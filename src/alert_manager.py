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
import smtplib
from email.mime.text import MIMEText
from typing import Dict, List, Optional
from urllib.parse import quote

import requests


class AlertManager:
    def __init__(self, config_path: Optional[str] = None):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        self.config_path = config_path or os.path.join(repo_root, "config", "alerts_config.json")

        self.config = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.config = json.load(f)
            except json.JSONDecodeError:
                self.config = {}

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
        if not topic:
            return
        server = (cfg.get("server") or "https://ntfy.sh").rstrip("/")
        # Allow slash-separated topics (e.g. self-hosted / user namespaces)
        url = f"{server}/{quote(topic, safe='/')}"
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
        }
        if title:
            headers["Title"] = title[:3900]
        headers["Priority"] = self._priority_header_value(cfg.get("priority", "default"))
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
        if not ntfy_cfg or not ntfy_cfg.get("enabled", False):
            return
        self._post_ntfy(title, message, ntfy_cfg)

    def send_buy_signal_alerts(self, signals: List[Dict]) -> None:
        """
        Send alerts for a list of newly created signals.
        Always prints to stdout; additionally sends email / ntfy / SMS if configured.
        """
        if not signals:
            return

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
            category_line = f"  Category: {event_category}\n" if event_category else ""
            body_lines.append(
                f"- {s.get('ticker')} | {s.get('confidence_level')} | event_date={event_date}\n"
                f"{category_line}"
                f"  Entry: {s.get('suggested_entry')}\n"
                f"  Stop:  {s.get('suggested_stop_loss')}\n"
                f"  Target:{s.get('risk_reward', {}).get('target_price')}\n"
                f"  Reasons: {', '.join(s.get('reasons', [])[:3])}\n"
            )
        body = "\n".join(body_lines)

        try:
            self._send_email(subject=subject, body=body)
        except Exception:
            pass

    def send_high_value_event_alerts(self, events: List[Dict]) -> None:
        """
        Send per-item alerts for newly triaged high-value events.
        Always logs to stdout; sends ntfy/email/SMS when configured.
        """
        if not events:
            return

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
            impact_score = e.get("impact_score", "")
            impact_like = e.get("impact_likelihood", "")
            distress_score = e.get("distress_score", "")
            distress_like = e.get("distress_likelihood", "")
            summary = (e.get("impact_summary", "") or "").strip()
            subject = f"Catastrophe Analyzer: High-Value Event {ticker}"
            body = (
                f"Ticker: {ticker}\n"
                f"Company: {company}\n"
                f"Date: {event_date}\n"
                f"Category: {category}\n"
                f"Impact: {impact_like} ({impact_score}/100)\n"
                f"Distress: {distress_like} ({distress_score}/100)\n"
                f"Summary: {summary}\n"
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

        try:
            self._send_ntfy(title=subject, message=body)
        except Exception:
            pass

        try:
            # SMS (Twilio) or ntfy via sms.provider — short summary
            first = signals[0]
            first_date = first.get("event_date", first.get("breach_date"))
            first_category = first.get("event_category", "")
            category_text = f", {first_category}" if first_category else ""
            sms_message = (
                f"BUY SIGNAL: {first.get('ticker')} ({first.get('confidence_level')}) "
                f"event {first_date}{category_text}"
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

