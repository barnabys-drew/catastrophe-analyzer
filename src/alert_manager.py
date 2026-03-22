"""
Alert Manager Module

Sends alerts when new buy signals are generated.
Default behavior: always prints alerts to stdout.
If `config/alerts_config.json` exists and enables email/SMS, it sends those too.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from typing import Dict, List, Optional

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

    def send_buy_signal_alerts(self, signals: List[Dict]) -> None:
        """
        Send alerts for a list of newly created signals.
        Always prints to stdout; additionally sends email/SMS if configured.
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
            print(f"- {ticker} | {conf_level} | entry={entry} target={target} | breach_date={s.get('breach_date')}")

        # Email/SMS (best-effort)
        subject = "Catastrophe Analyzer: New Buy Signal(s)"
        body_lines = ["New buy signal(s) have been generated:\n"]
        for s in signals:
            body_lines.append(
                f"- {s.get('ticker')} | {s.get('confidence_level')} | breach_date={s.get('breach_date')}\n"
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

        try:
            # SMS: one message summarizing the first signal
            first = signals[0]
            sms_message = f"BUY SIGNAL: {first.get('ticker')} ({first.get('confidence_level')}) breach {first.get('breach_date')}"
            self._send_sms_twilio(sms_message)
        except Exception:
            pass

