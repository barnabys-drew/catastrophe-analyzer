"""
Alert Manager Module

Sends alerts when new buy signals are generated.
Default behavior: always prints alerts to stdout.
If `config/alerts_config.json` exists and enables email, ntfy, or SMS (Twilio), it sends those too.

ntfy.sh (or a self-hosted ntfy server) provides push notifications to the ntfy app — a practical
replacement for SMS without Twilio.
"""

import os
import json
import re
import smtplib
import uuid
from datetime import datetime
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests


class AlertManager:
    def __init__(self, config_path: Optional[str] = None):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        self.repo_root = repo_root
        self.config_path = config_path or os.path.join(repo_root, "config", "alerts_config.json")

        self.config = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.config = json.load(f)
            except json.JSONDecodeError:
                self.config = {}

        # Env overrides for local dev (no phone / no ntfy round-trip).
        env_preview = os.environ.get("CATASTROPHE_LOCAL_ALERT_PREVIEW", "").strip().lower()
        if env_preview in ("1", "true", "yes"):
            self.config.setdefault("local_alert_preview", {})
            self.config["local_alert_preview"]["enabled"] = True
        env_local_only = os.environ.get("CATASTROPHE_ALERTS_LOCAL_ONLY", "").strip().lower()
        if env_local_only in ("1", "true", "yes"):
            self.config.setdefault("local_alert_preview", {})
            self.config["local_alert_preview"]["enabled"] = True
            self.config["local_alert_preview"]["disable_ntfy_http"] = True

    def _local_preview_settings(self) -> Tuple[bool, str, bool, bool]:
        """enabled, directory (abs path), disable_ntfy_http, include_url_section."""
        raw = (self.config or {}).get("local_alert_preview") or {}
        enabled = bool(raw.get("enabled", False))
        rel = (raw.get("directory") or "data/alert_previews").strip()
        if not os.path.isabs(rel):
            rel = os.path.join(self.repo_root, rel)
        disable_http = bool(raw.get("disable_ntfy_http", False))
        urls_section = bool(raw.get("include_extracted_urls_section", True))
        return enabled, rel, disable_http, urls_section

    @staticmethod
    def _extract_http_urls(text: str) -> List[str]:
        if not (text or "").strip():
            return []
        # Greedy but trim common trailing punctuation from prose.
        found = re.findall(r"https?://[^\s<>\[\]()\"']+", text)
        out: List[str] = []
        for u in found:
            u = u.rstrip(").,;]")
            if u not in out:
                out.append(u)
        return out

    def _write_local_alert_preview(
        self,
        title: str,
        message: str,
        *,
        server: str = "",
        topic: str = "",
        priority: str = "",
    ) -> None:
        enabled, directory, _, include_urls = self._local_preview_settings()
        if not enabled:
            return
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        short = uuid.uuid4().hex[:8]
        path = os.path.join(directory, f"{stamp}-{short}.txt")
        urls = self._extract_http_urls(message) if include_urls else []
        lines = [
            "Catastrophe Analyzer — local alert preview (same payload as ntfy)",
            f"Written: {datetime.now().isoformat()}",
            "",
            f"ntfy server: {server or '(n/a)'}",
            f"ntfy topic: {topic or '(n/a)'}",
            f"priority: {priority or '(n/a)'}",
            "",
            "===== Title (ntfy header) =====",
            title or "(no title)",
            "",
        ]
        if urls:
            lines.extend(
                [
                    "===== COPY-PASTE URLS (one per line) =====",
                    *urls,
                    "",
                ]
            )
        lines.extend(
            [
                "===== Message body (ntfy body) =====",
                message,
                "",
            ]
        )
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError:
            return
        try:
            latest = os.path.join(directory, "LATEST.txt")
            with open(latest, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError:
            pass
        print(f"[local_alert_preview] wrote {path}")

    def _send_email(self, subject: str, body: str) -> None:
        email_cfg = self.config.get("alert_channels", {}).get("email", {}) if self.config else {}
        if not email_cfg or not email_cfg.get("enabled", False):
            return

        smtp_server = email_cfg.get("smtp_server")
        smtp_port = int(email_cfg.get("smtp_port", 587))
        email_from = email_cfg.get("email_from")
        email_to = email_cfg.get("email_to")
        require_auth = bool(email_cfg.get("require_auth", False))

        if not (smtp_server and email_from and email_to):
            return

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = email_from
        msg["To"] = email_to

        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            if require_auth:
                username = email_cfg.get("username")
                password = email_cfg.get("password")
                if username and password:
                    server.login(username, password)
            server.sendmail(email_from, [email_to], msg.as_string())

    def _send_sms_twilio(self, message: str) -> None:
        sms_cfg = self.config.get("alert_channels", {}).get("sms", {}) if self.config else {}
        if not sms_cfg or not sms_cfg.get("enabled", False):
            return
        if sms_cfg.get("provider") != "twilio":
            return

        account_sid = sms_cfg.get("account_sid")
        auth_token = sms_cfg.get("auth_token")
        from_number = sms_cfg.get("from_number")
        to_number = sms_cfg.get("to_number")
        if not all([account_sid, auth_token, from_number, to_number]):
            return

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {
            "From": from_number,
            "To": to_number,
            "Body": message,
        }

        try:
            requests.post(url, data=data, auth=(account_sid, auth_token), timeout=15).raise_for_status()
        except Exception:
            # Never crash the monitor on alert failures
            return

    def _priority_header_value(self, raw) -> str:
        """Map config priority to ntfy X-Priority (1–5)."""
        if isinstance(raw, int) and 1 <= raw <= 5:
            return str(raw)
        if isinstance(raw, str) and raw.isdigit() and 1 <= int(raw) <= 5:
            return raw
        if not isinstance(raw, str):
            return "3"
        key = raw.lower().strip()
        mapped = {"min": 1, "low": 2, "default": 3, "normal": 3, "high": 4, "urgent": 5, "max": 5}
        return str(mapped.get(key, 3))

    def _post_ntfy(self, title: str, message: str, cfg: Dict) -> None:
        """
        POST to ntfy (https://ntfy.sh or self-hosted). cfg: topic, server, optional token, priority.
        """
        topic = (cfg.get("topic") or "").strip()
        preview_on, _, disable_http, _ = self._local_preview_settings()
        if not topic and not preview_on:
            return
        server = (cfg.get("server") or "https://ntfy.sh").rstrip("/")
        pri = self._priority_header_value(cfg.get("priority", "default"))
        self._write_local_alert_preview(
            title,
            message,
            server=server,
            topic=topic or "(no topic — check alerts_config.json)",
            priority=pri,
        )
        if not topic:
            return
        if disable_http:
            return
        # Allow slash-separated topics (e.g. self-hosted / user namespaces)
        url = f"{server}/{quote(topic, safe='/')}"
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
        }
        if title:
            headers["Title"] = title[:3900]
        headers["Priority"] = pri
        token = (cfg.get("token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            requests.post(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                timeout=15,
            ).raise_for_status()
        except Exception:
            return

    def _send_ntfy(self, title: str, message: str) -> None:
        ntfy_cfg = self.config.get("alert_channels", {}).get("ntfy", {}) if self.config else {}
        preview_on, _, _, _ = self._local_preview_settings()
        if not ntfy_cfg:
            return
        if not ntfy_cfg.get("enabled", False) and not preview_on:
            return
        self._post_ntfy(title, message, ntfy_cfg)

    @staticmethod
    def _article_title(title: str, url: str) -> str:
        """Return human-readable article title fallback."""
        clean_title = (title or "").strip()
        clean_url = (url or "").strip()
        if clean_title:
            return clean_title
        if clean_url:
            return clean_url
        return "N/A"

    @staticmethod
    def _article_url_block(article_label: str, article_url: str, line_prefix: str = "  ") -> str:
        """
        Format article title + URL with extra vertical space so mobile tap/selection
        does not grab neighboring lines (Issue, Reasons, etc.).
        """
        url = (article_url or "").strip()
        label = (article_label or "").strip() or "N/A"
        p = line_prefix
        if not url:
            return f"{p}Article: {label}\n"
        sep = p + "────────────────────────────────"
        return (
            "\n"
            f"{sep}\n"
            f"{p}Article:\n"
            f"{p}{label}\n"
            "\n\n\n"
            f"{p}{url}\n"
            "\n\n\n"
            f"{sep}\n"
            "\n"
        )

    @staticmethod
    def _dedupe_one_company_per_ticker(items: List[Dict]) -> List[Dict]:
        """
        Keep a single record per ticker to avoid duplicate company rows in alerts.
        Prefer the richest row by number of populated fields.
        """
        chosen: Dict[str, Dict] = {}
        for item in items:
            ticker = str(item.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            current = chosen.get(ticker)
            if not current:
                chosen[ticker] = item
                continue
            current_score = sum(1 for _, v in current.items() if str(v).strip())
            item_score = sum(1 for _, v in item.items() if str(v).strip())
            if item_score >= current_score:
                chosen[ticker] = item
        return list(chosen.values())

    def send_buy_signal_alerts(self, signals: List[Dict]) -> None:
        """
        Send alerts for a list of newly created signals.
        Always prints to stdout; additionally sends email / ntfy / SMS if configured.
        """
        if not signals:
            return
        signals = self._dedupe_one_company_per_ticker(signals)

        # Console alert (works immediately in Docker logs)
        print("\n" + "=" * 80)
        print("NEW BUY SIGNAL(S)")
        print("=" * 80)
        for s in signals:
            ticker = s.get("ticker", "")
            conf_level = s.get("confidence_level", "")
            entry = s.get("suggested_entry", s.get("entry_price", ""))
            target = s.get("risk_reward", {}).get("target_price", s.get("target_price", ""))
            event_date = s.get("event_date", s.get("breach_date"))
            event_category = s.get("event_category", "")
            category_text = f" | category={event_category}" if event_category else ""
            print(f"- {ticker} | {conf_level} | entry={entry} target={target} | event_date={event_date}{category_text}")

        # Email / ntfy / SMS (best-effort)
        subject = "Catastrophe Analyzer: New Buy Signal(s)"
        body_lines = ["New buy signal(s) have been generated:\n"]
        for s in signals:
            event_date = s.get("event_date", s.get("breach_date"))
            event_category = s.get("event_category", "")
            event_subtype = s.get("event_subtype", "")
            issue_summary = (s.get("issue_summary", "") or s.get("impact_summary", "")).strip()
            article_title = (s.get("title", "") or "").strip()
            article_url = (s.get("url", "") or "").strip()
            article_label = self._article_title(article_title, article_url)
            article_block = self._article_url_block(article_label, article_url)
            category_line = f"  Category: {event_category}\n" if event_category else ""
            subtype_line = f"  Subtype: {event_subtype}\n" if event_subtype else ""
            issue_line = f"  Issue: {issue_summary}\n" if issue_summary else ""
            body_lines.append(
                f"- {s.get('ticker')} | {s.get('confidence_level')} | event_date={event_date}\n"
                f"{category_line}"
                f"{subtype_line}"
                f"{issue_line}"
                f"\n"
                f"  Entry: {s.get('suggested_entry')}\n"
                f"  Stop:  {s.get('suggested_stop_loss')}\n"
                f"  Target:{s.get('risk_reward', {}).get('target_price')}\n"
                f"{article_block}"
                f"  Reasons: {', '.join(s.get('reasons', [])[:3])}\n"
            )
        body = "\n".join(body_lines)

        try:
            self._send_email(subject=subject, body=body)
        except Exception:
            pass
        try:
            self._send_ntfy(title=subject, message=body)
        except Exception:
            pass

        try:
            # SMS (Twilio) or ntfy via sms.provider — short summary
            first = signals[0]
            first_date = first.get("event_date", first.get("breach_date"))
            first_category = first.get("event_category", "")
            first_subtype = first.get("event_subtype", "")
            category_text = f", {first_category}" if first_category else ""
            subtype_text = f" [{first_subtype}]" if first_subtype else ""
            sms_message = (
                f"BUY SIGNAL: {first.get('ticker')} ({first.get('confidence_level')}) "
                f"event {first_date}{category_text}{subtype_text}"
            )
            sms_cfg = self.config.get("alert_channels", {}).get("sms", {}) if self.config else {}
            if sms_cfg and sms_cfg.get("enabled", False):
                provider = (sms_cfg.get("provider") or "twilio").lower()
                if provider == "ntfy":
                    if len(signals) > 1:
                        sms_message = f"{sms_message} (+{len(signals) - 1} more)"
                    self._post_ntfy(title=subject[:200], message=sms_message, cfg=sms_cfg)
                else:
                    self._send_sms_twilio(sms_message)
        except Exception:
            pass

    def send_high_value_event_alerts(self, events: List[Dict]) -> None:
        """
        Send per-item alerts for newly triaged high-value events.
        Always logs to stdout; sends ntfy/email/SMS when configured.
        """
        if not events:
            return
        events = self._dedupe_one_company_per_ticker(events)

        print("\n" + "=" * 80)
        print("NEW HIGH-VALUE EVENT(S)")
        print("=" * 80)
        for e in events:
            print(
                f"- {e.get('ticker', '')} | {e.get('event_category', '')} | "
                f"impact={e.get('impact_likelihood', '')} {e.get('impact_score', '')}/100 | "
                f"distress={e.get('distress_likelihood', '')} {e.get('distress_score', '')}/100"
            )

        for e in events:
            ticker = e.get("ticker", "")
            company = e.get("company", "")
            event_date = e.get("event_date", "")
            category = e.get("event_category", "")
            event_subtype = e.get("event_subtype", "")
            impact_score = e.get("impact_score", "")
            impact_like = e.get("impact_likelihood", "")
            distress_score = e.get("distress_score", "")
            distress_like = e.get("distress_likelihood", "")
            summary = (e.get("impact_summary", "") or "").strip()
            article_title = (e.get("title", "") or "").strip()
            article_url = (e.get("url", "") or "").strip()
            article_label = self._article_title(article_title, article_url)
            article_block_hv = self._article_url_block(article_label, article_url, line_prefix="")
            subject = f"Catastrophe Analyzer: High-Value Event {ticker}"
            body = (
                f"Ticker: {ticker}\n"
                f"Company: {company}\n"
                f"Date: {event_date}\n"
                f"Category: {category}\n"
                f"Subtype: {event_subtype}\n"
                f"Impact: {impact_like} ({impact_score}/100)\n"
                f"Distress: {distress_like} ({distress_score}/100)\n"
                f"Summary: {summary}\n"
                f"\n"
                f"{article_block_hv}"
            )

            try:
                self._send_email(subject=subject, body=body)
            except Exception:
                pass

            try:
                self._send_ntfy(title=subject, message=body)
            except Exception:
                pass

            try:
                sms_cfg = self.config.get("alert_channels", {}).get("sms", {}) if self.config else {}
                if sms_cfg and sms_cfg.get("enabled", False):
                    provider = (sms_cfg.get("provider") or "twilio").lower()
                    sms_message = (
                        f"HIGH-VALUE EVENT: {ticker} {category} "
                        f"impact {impact_like}({impact_score}) distress {distress_like}({distress_score})"
                    )
                    if provider == "ntfy":
                        self._post_ntfy(title=subject[:200], message=sms_message, cfg=sms_cfg)
                    else:
                        self._send_sms_twilio(sms_message)
            except Exception:
                pass


