"""
Alert Manager Module

Sends alerts when new buy signals are generated.
Default behavior: always prints alerts to stdout.
If `config/alerts_config.json` exists and enables email, ntfy, or SMS (Twilio), it sends those too.

ntfy.sh (or a self-hosted ntfy server) provides push notifications to the ntfy app — a practical
replacement for SMS without Twilio.
"""

import logging
import os
import json
import re
import smtplib
import time
import uuid
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

import requests
from signal_generator import compute_signal_rank_score


class AlertManager:
    _TRANSIENT_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

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

    @staticmethod
    def _delivery_result(
        *,
        channel: str,
        attempted: bool,
        success: bool,
        skipped: bool = False,
        status_code: Optional[int] = None,
        error: str = "",
        attempts: int = 0,
        retry_exhausted: bool = False,
    ) -> Dict[str, Any]:
        return {
            "channel": channel,
            "attempted": bool(attempted),
            "success": bool(success),
            "skipped": bool(skipped),
            "status_code": status_code,
            "error": (error or "").strip(),
            "attempts": int(attempts),
            "retry_exhausted": bool(retry_exhausted),
        }

    def _retry_policy(self) -> Tuple[int, float]:
        """
        Returns (max_retries, backoff_seconds) where max_retries excludes first attempt.
        """
        delivery_cfg = (self.config or {}).get("delivery") or {}
        max_retries_raw = (
            os.environ.get("CATASTROPHE_ALERT_MAX_RETRIES")
            or delivery_cfg.get("max_retries")
            or 2
        )
        backoff_raw = (
            os.environ.get("CATASTROPHE_ALERT_RETRY_BACKOFF_SECONDS")
            or delivery_cfg.get("retry_backoff_seconds")
            or 1.0
        )
        try:
            max_retries = max(0, int(max_retries_raw))
        except (TypeError, ValueError):
            max_retries = 2
        try:
            backoff = max(0.0, float(backoff_raw))
        except (TypeError, ValueError):
            backoff = 1.0
        return max_retries, backoff

    @classmethod
    def _is_transient_status(cls, code: Optional[int]) -> bool:
        return bool(code in cls._TRANSIENT_HTTP_STATUS)

    def _post_with_retries(
        self,
        *,
        url: str,
        data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        auth: Any = None,
        timeout: int = 15,
        channel: str,
    ) -> Dict[str, Any]:
        max_retries, backoff_seconds = self._retry_policy()
        attempts = 0
        last_error = ""
        last_status: Optional[int] = None
        retry_exhausted = False

        while attempts <= max_retries:
            attempts += 1
            try:
                response = requests.post(
                    url,
                    data=data,
                    headers=headers,
                    auth=auth,
                    timeout=timeout,
                )
                last_status = int(response.status_code)
                if 200 <= response.status_code < 300:
                    return self._delivery_result(
                        channel=channel,
                        attempted=True,
                        success=True,
                        status_code=last_status,
                        attempts=attempts,
                    )
                last_error = f"HTTP {response.status_code}: {(response.text or '')[:200]}"
                if not self._is_transient_status(last_status) or attempts > max_retries:
                    retry_exhausted = attempts > max_retries and self._is_transient_status(last_status)
                    break
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempts > max_retries:
                    retry_exhausted = True
                    break
            if backoff_seconds > 0:
                time.sleep(backoff_seconds * attempts)

        return self._delivery_result(
            channel=channel,
            attempted=True,
            success=False,
            status_code=last_status,
            error=last_error or "request failed",
            attempts=attempts,
            retry_exhausted=retry_exhausted,
        )

    @staticmethod
    def _summarize_delivery_results(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        summary: Dict[str, Dict[str, int]] = {}
        for result in results:
            channel = str(result.get("channel") or "unknown")
            bucket = summary.setdefault(
                channel, {"attempted": 0, "success": 0, "failed": 0, "skipped": 0}
            )
            if result.get("attempted"):
                bucket["attempted"] += 1
            if result.get("success"):
                bucket["success"] += 1
            elif result.get("skipped"):
                bucket["skipped"] += 1
            elif result.get("attempted"):
                bucket["failed"] += 1
        return summary

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

    def _send_email(self, subject: str, body: str) -> Dict[str, Any]:
        email_cfg = self.config.get("alert_channels", {}).get("email", {}) if self.config else {}
        if not email_cfg or not email_cfg.get("enabled", False):
            return self._delivery_result(
                channel="email", attempted=False, success=False, skipped=True, error="email disabled"
            )

        smtp_server = email_cfg.get("smtp_server")
        smtp_port = int(email_cfg.get("smtp_port", 587))
        email_from = email_cfg.get("email_from")
        email_to = email_cfg.get("email_to")
        require_auth = bool(email_cfg.get("require_auth", False))

        if not (smtp_server and email_from and email_to):
            return self._delivery_result(
                channel="email",
                attempted=False,
                success=False,
                skipped=True,
                error="email missing smtp_server/email_from/email_to",
            )

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = email_from
        msg["To"] = email_to

        try:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                if require_auth:
                    username = email_cfg.get("username")
                    password = os.environ.get("CATASTROPHE_EMAIL_PASSWORD") or email_cfg.get("password")
                    if username and password:
                        server.login(username, password)
                server.sendmail(email_from, [email_to], msg.as_string())
            return self._delivery_result(channel="email", attempted=True, success=True, attempts=1)
        except (OSError, smtplib.SMTPException) as exc:
            return self._delivery_result(
                channel="email", attempted=True, success=False, attempts=1, error=str(exc)
            )

    def _send_sms_twilio(self, message: str) -> Dict[str, Any]:
        sms_cfg = self.config.get("alert_channels", {}).get("sms", {}) if self.config else {}
        if not sms_cfg or not sms_cfg.get("enabled", False):
            return self._delivery_result(
                channel="sms", attempted=False, success=False, skipped=True, error="sms disabled"
            )
        if sms_cfg.get("provider") != "twilio":
            return self._delivery_result(
                channel="sms",
                attempted=False,
                success=False,
                skipped=True,
                error="sms provider is not twilio",
            )

        account_sid = sms_cfg.get("account_sid")
        auth_token = sms_cfg.get("auth_token")
        from_number = sms_cfg.get("from_number")
        to_number = sms_cfg.get("to_number")
        if not all([account_sid, auth_token, from_number, to_number]):
            return self._delivery_result(
                channel="sms",
                attempted=False,
                success=False,
                skipped=True,
                error="twilio credentials/numbers missing",
            )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {
            "From": from_number,
            "To": to_number,
            "Body": message,
        }

        return self._post_with_retries(
            url=url,
            data=data,
            auth=(account_sid, auth_token),
            timeout=15,
            channel="sms",
        )

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

    def _post_ntfy(self, title: str, message: str, cfg: Dict) -> Dict[str, Any]:
        """
        POST to ntfy (https://ntfy.sh or self-hosted). cfg: topic, server, optional token, priority.
        """
        topic = (cfg.get("topic") or "").strip()
        preview_on, _, disable_http, _ = self._local_preview_settings()
        if not topic and not preview_on:
            return self._delivery_result(
                channel="ntfy",
                attempted=False,
                success=False,
                skipped=True,
                error="ntfy topic missing and preview disabled",
            )
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
            return self._delivery_result(
                channel="ntfy",
                attempted=False,
                success=False,
                skipped=True,
                error="ntfy topic missing",
            )
        if disable_http:
            return self._delivery_result(
                channel="ntfy",
                attempted=False,
                success=False,
                skipped=True,
                error="ntfy http disabled by local preview settings",
            )
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

        return self._post_with_retries(
            url=url,
            data=message.encode("utf-8"),
            headers=headers,
            timeout=15,
            channel="ntfy",
        )

    def _send_ntfy(self, title: str, message: str) -> Dict[str, Any]:
        ntfy_cfg = self.config.get("alert_channels", {}).get("ntfy", {}) if self.config else {}
        preview_on, _, _, _ = self._local_preview_settings()
        if not ntfy_cfg:
            return self._delivery_result(
                channel="ntfy",
                attempted=False,
                success=False,
                skipped=True,
                error="ntfy config missing",
            )
        if not ntfy_cfg.get("enabled", False) and not preview_on:
            return self._delivery_result(
                channel="ntfy",
                attempted=False,
                success=False,
                skipped=True,
                error="ntfy disabled",
            )
        return self._post_ntfy(title, message, ntfy_cfg)

    def _account_policy_for_event(self, event_category: str) -> Dict:
        """
        Shared account-policy schema used by outbound alerts.
        """
        cfg = (self.config or {}).get("account_policy") or {}
        category_map = cfg.get("event_category_targets") if isinstance(cfg, dict) else {}
        routed_account = None
        if isinstance(category_map, dict):
            routed_account = category_map.get(event_category)
        account_type = routed_account or cfg.get("default_account_type") or "Brokerage"
        return {
            "tool": "catastrophe-analyzer",
            "account_type": str(account_type),
            "account_label": str(cfg.get("account_label", "Event-driven sleeve")),
            "route_key": str(cfg.get("route_key", "event_opportunity_watch")),
            "objective": "Surface event-driven opportunities with impact/distress triage",
        }

    @staticmethod
    def _alert_mode() -> str:
        mode = (os.environ.get("CATASTROPHE_ALERT_MODE") or "balanced").strip().lower()
        if mode in {"strict", "balanced", "broad"}:
            return mode
        return "balanced"

    @classmethod
    def _filter_buy_signals_for_mode(cls, signals: List[Dict]) -> List[Dict]:
        mode = cls._alert_mode()
        if mode == "strict":
            kept = []
            for s in signals:
                lvl = str(s.get("confidence_level", "")).upper().strip()
                conf = cls._to_float(s.get("confidence"), default=0.0)
                if lvl == "HIGH" or conf >= 85:
                    kept.append(s)
            signals = kept
        elif mode == "balanced":
            kept = []
            for s in signals:
                lvl = str(s.get("confidence_level", "")).upper().strip()
                conf = cls._to_float(s.get("confidence"), default=0.0)
                if lvl in {"HIGH", "MEDIUM"} and conf >= 70:
                    kept.append(s)
            signals = kept

        env_limit = os.environ.get("CATASTROPHE_ALERT_MAX_SIGNALS_PER_CYCLE")
        default_limit = "6" if mode == "broad" else "4" if mode == "balanced" else "2"
        try:
            max_count = max(1, int(env_limit or default_limit))
        except ValueError:
            max_count = int(default_limit)
        return signals[:max_count]

    @classmethod
    def _filter_high_value_events_for_mode(cls, events: List[Dict]) -> List[Dict]:
        mode = cls._alert_mode()
        if mode == "broad":
            min_impact, min_distress = 55, 30
            max_count = 8
        elif mode == "strict":
            min_impact, min_distress = 75, 55
            max_count = 3
        else:
            min_impact, min_distress = 60, 35
            max_count = 5

        env_limit = os.environ.get("CATASTROPHE_ALERT_MAX_EVENTS_PER_CYCLE")
        if env_limit:
            try:
                max_count = max(1, int(env_limit))
            except ValueError:
                pass

        filtered = []
        for event in events:
            impact = cls._to_float(event.get("impact_score"), default=0.0)
            distress = cls._to_float(event.get("distress_score"), default=0.0)
            if impact >= min_impact and distress >= min_distress:
                filtered.append(event)
        return filtered[:max_count]

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

    @staticmethod
    def _to_float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _signal_strength_score(cls, signal: Dict) -> float:
        """
        Numeric strength score for sorting buy-signal alerts.
        Prefers explicit confidence score; falls back to confidence_level.
        """
        score = cls._to_float(signal.get("confidence"), default=-1.0)
        if score >= 0:
            return score
        score = cls._to_float(signal.get("confidence_score"), default=-1.0)
        if score >= 0:
            return score
        level = str(signal.get("confidence_level", "")).upper().strip()
        return {"HIGH": 90.0, "MEDIUM": 60.0, "LOW": 30.0}.get(level, 0.0)

    @classmethod
    def _signal_price_for_sort(cls, signal: Dict) -> float:
        """
        Best-effort comparable price for ranking lower-risk entries first.
        """
        for key in ("price", "suggested_entry", "entry_price"):
            value = cls._to_float(signal.get(key), default=float("inf"))
            if value != float("inf"):
                return value
        return float("inf")

    @classmethod
    def _order_signals_for_alerts(cls, signals: List[Dict]) -> List[Dict]:
        """
        Order by canonical signal rank, then lower stock price.
        """
        return sorted(
            signals,
            key=lambda s: (
                -compute_signal_rank_score(s),
                cls._signal_price_for_sort(s),
                str(s.get("ticker", "")),
            ),
        )

    def send_buy_signal_alerts(self, signals: List[Dict], *, emit_console: bool = True) -> Dict[str, Any]:
        """
        Send alerts for a list of newly created signals.
        Prints to stdout when emit_console=True; always sends email / ntfy / SMS if configured.
        """
        if not signals:
            return {
                "kind": "buy_signals",
                "items_attempted": 0,
                "items_delivered": 0,
                "delivery_results": [],
                "channels": {},
            }
        signals = self._dedupe_one_company_per_ticker(signals)
        signals = self._order_signals_for_alerts(signals)
        signals = self._filter_buy_signals_for_mode(signals)
        if not signals:
            return {
                "kind": "buy_signals",
                "items_attempted": 0,
                "items_delivered": 0,
                "delivery_results": [],
                "channels": {},
            }
        alert_mode = self._alert_mode()

        if emit_console:
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
        body_lines = [
            "New buy signal(s) have been generated:\n",
            f"Notification profile: {alert_mode}",
            "",
        ]
        for s in signals:
            event_date = s.get("event_date", s.get("breach_date"))
            event_category = s.get("event_category", "")
            account_policy = self._account_policy_for_event(event_category)
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
                f"  Account: {account_policy['account_type']} / {account_policy['account_label']}\n"
                f"  Route: {account_policy['route_key']}\n"
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

        delivery_results: List[Dict[str, Any]] = []
        delivery_results.append(self._send_email(subject=subject, body=body))
        delivery_results.append(self._send_ntfy(title=subject, message=body))

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
                delivery_results.append(
                    self._post_ntfy(title=subject[:200], message=sms_message, cfg=sms_cfg)
                )
            else:
                delivery_results.append(self._send_sms_twilio(sms_message))
        else:
            delivery_results.append(
                self._delivery_result(
                    channel="sms",
                    attempted=False,
                    success=False,
                    skipped=True,
                    error="sms disabled",
                )
            )

        delivered = any(bool(r.get("success")) for r in delivery_results)
        failed = [r for r in delivery_results if r.get("attempted") and not r.get("success")]
        if failed:
            logger.warning("Buy-signal alert partial failures: %s", failed)
        return {
            "kind": "buy_signals",
            "items_attempted": len(signals),
            "items_delivered": 1 if delivered else 0,
            "delivery_results": delivery_results,
            "channels": self._summarize_delivery_results(delivery_results),
        }

    def send_high_value_event_alerts(self, events: List[Dict], *, emit_console: bool = True) -> Dict[str, Any]:
        """
        Send per-item alerts for newly triaged high-value events.
        Logs to stdout when emit_console=True; sends ntfy/email/SMS when configured.
        """
        if not events:
            return {
                "kind": "high_value_events",
                "items_attempted": 0,
                "items_delivered": 0,
                "event_results": [],
                "channels": {},
            }
        events = self._dedupe_one_company_per_ticker(events)
        events = self._filter_high_value_events_for_mode(events)
        if not events:
            return {
                "kind": "high_value_events",
                "items_attempted": 0,
                "items_delivered": 0,
                "event_results": [],
                "channels": {},
            }

        event_results: List[Dict[str, Any]] = []

        if emit_console:
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
            account_policy = self._account_policy_for_event(category)
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
                f"Account: {account_policy['account_type']} / {account_policy['account_label']}\n"
                f"Route: {account_policy['route_key']}\n"
                f"Date: {event_date}\n"
                f"Category: {category}\n"
                f"Subtype: {event_subtype}\n"
                f"Impact: {impact_like} ({impact_score}/100)\n"
                f"Distress: {distress_like} ({distress_score}/100)\n"
                f"Summary: {summary}\n"
                f"\n"
                f"{article_block_hv}"
            )

            results_for_event: List[Dict[str, Any]] = []
            results_for_event.append(self._send_email(subject=subject, body=body))
            results_for_event.append(self._send_ntfy(title=subject, message=body))

            sms_cfg = self.config.get("alert_channels", {}).get("sms", {}) if self.config else {}
            if sms_cfg and sms_cfg.get("enabled", False):
                provider = (sms_cfg.get("provider") or "twilio").lower()
                sms_message = (
                    f"HIGH-VALUE EVENT: {ticker} {category} "
                    f"impact {impact_like}({impact_score}) distress {distress_like}({distress_score})"
                )
                if provider == "ntfy":
                    results_for_event.append(
                        self._post_ntfy(title=subject[:200], message=sms_message, cfg=sms_cfg)
                    )
                else:
                    results_for_event.append(self._send_sms_twilio(sms_message))
            else:
                results_for_event.append(
                    self._delivery_result(
                        channel="sms",
                        attempted=False,
                        success=False,
                        skipped=True,
                        error="sms disabled",
                    )
                )

            delivered = any(bool(r.get("success")) for r in results_for_event)
            if not delivered:
                logger.warning(
                    "High-value event had no successful channel (%s): %s",
                    ticker,
                    results_for_event,
                )
            event_results.append(
                {
                    "event_key": (e.get("event_key") or "").strip(),
                    "ticker": ticker,
                    "delivered": delivered,
                    "delivery_results": results_for_event,
                }
            )

        all_results = [
            result
            for event_result in event_results
            for result in event_result.get("delivery_results", [])
        ]
        delivered_count = sum(1 for event_result in event_results if event_result.get("delivered"))
        return {
            "kind": "high_value_events",
            "items_attempted": len(events),
            "items_delivered": delivered_count,
            "event_results": event_results,
            "channels": self._summarize_delivery_results(all_results),
        }


