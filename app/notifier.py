"""
Notifier module for KubeAlert.
Constructs and dispatches HTML and plain-text email alerts via SMTP.
"""

import html
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from analyzer import PodIssue
from config import Config

logger = logging.getLogger("kubealert.notifier")


class EmailNotifier:
    def __init__(self):
        self.smtp_host = Config.SMTP_HOST
        self.smtp_port = Config.SMTP_PORT
        self.smtp_user = Config.SMTP_USER
        self.smtp_password = Config.SMTP_PASSWORD
        self.use_tls = Config.SMTP_USE_TLS
        self.use_ssl = Config.SMTP_USE_SSL
        self.from_email = Config.ALERT_FROM_EMAIL
        self.to_email = Config.ALERT_TO_EMAIL

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.to_email)

    def send_alert(self, issue: PodIssue, logs: Optional[str] = None):
        """Dispatches an email alert or logs to stdout if SMTP is not configured."""
        subject = f"[KubeAlert] {issue.reason} on pod {issue.namespace}/{issue.pod_name}"

        if not self.is_configured():
            logger.warning(
                "SMTP not configured. Alert would be sent: %s | Container: %s | Message: %s",
                subject,
                issue.container_name,
                issue.message,
            )
            return

        plain_text = self._build_plain_text(issue, logs)
        html_content = self._build_html(issue, logs)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = self.to_email
        msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            logger.info("Sending alert email to %s for %s/%s (%s)...", self.to_email, issue.namespace, issue.pod_name, issue.reason)
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)

            with server:
                server.ehlo()
                if self.use_tls and not self.use_ssl:
                    server.starttls()
                    server.ehlo()

                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)

                recipients = [e.strip() for e in self.to_email.split(",") if e.strip()]
                server.sendmail(self.from_email, recipients, msg.as_string())

            logger.info("Alert email successfully dispatched for %s/%s!", issue.namespace, issue.pod_name)
        except Exception as exc:
            logger.error("Failed to send email alert via SMTP (%s:%d): %s", self.smtp_host, self.smtp_port, exc)

    def _build_plain_text(self, issue: PodIssue, logs: Optional[str] = None) -> str:
        date_str = datetime.fromtimestamp(issue.detected_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"KubeAlert - Kubernetes Pod Issue Detected",
            f"==========================================",
            f"Reason:         {issue.reason}",
            f"Namespace:      {issue.namespace}",
            f"Pod:            {issue.pod_name}",
            f"Container:      {issue.container_name}",
            f"Phase:          {issue.phase}",
            f"Restart Count:  {issue.restart_count}",
            f"Exit Code:      {issue.exit_code if issue.exit_code is not None else 'N/A'}",
            f"Detected At:    {date_str}",
            f"Details:        {issue.message}",
            "",
        ]
        if logs:
            lines.extend([
                "Recent Container Logs:",
                "----------------------",
                logs,
                ""
            ])
        lines.append("Sent by KubeAlert monitoring system.")
        return "\n".join(lines)

    def _build_html(self, issue: PodIssue, logs: Optional[str] = None) -> str:
        date_str = datetime.fromtimestamp(issue.detected_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        badge_color = "#e53e3e" if issue.reason in ("OOMKilled", "CrashLoopBackOff") else "#dd6b20"

        logs_section = ""
        if logs:
            escaped_logs = html.escape(logs)
            logs_section = f"""
            <h3 style="margin-top: 25px; color: #2d3748; font-size: 16px;">Recent Container Logs</h3>
            <pre style="background: #1a202c; color: #e2e8f0; padding: 12px; border-radius: 6px; font-size: 13px; overflow-x: auto; font-family: monospace; line-height: 1.4;">{escaped_logs}</pre>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>KubeAlert Notification</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7fafc; margin: 0; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); padding: 24px;">
    
    <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #edf2f7; padding-bottom: 12px; margin-bottom: 20px;">
      <h2 style="margin: 0; color: #1a202c; font-size: 20px;">🚨 Kubernetes Issue Detected</h2>
      <span style="background: {badge_color}; color: #ffffff; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: bold;">
        {html.escape(issue.reason)}
      </span>
    </div>

    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
      <tr>
        <td style="padding: 8px 0; color: #718096; font-size: 14px; width: 35%;">Namespace:</td>
        <td style="padding: 8px 0; color: #2d3748; font-size: 14px; font-weight: 600;">{html.escape(issue.namespace)}</td>
      </tr>
      <tr>
        <td style="padding: 8px 0; color: #718096; font-size: 14px;">Pod:</td>
        <td style="padding: 8px 0; color: #2d3748; font-size: 14px; font-weight: 600;">{html.escape(issue.pod_name)}</td>
      </tr>
      <tr>
        <td style="padding: 8px 0; color: #718096; font-size: 14px;">Container:</td>
        <td style="padding: 8px 0; color: #2d3748; font-size: 14px; font-weight: 600;">{html.escape(issue.container_name)}</td>
      </tr>
      <tr>
        <td style="padding: 8px 0; color: #718096; font-size: 14px;">Phase:</td>
        <td style="padding: 8px 0; color: #2d3748; font-size: 14px;">{html.escape(issue.phase)}</td>
      </tr>
      <tr>
        <td style="padding: 8px 0; color: #718096; font-size: 14px;">Restart Count:</td>
        <td style="padding: 8px 0; color: #2d3748; font-size: 14px;">{issue.restart_count}</td>
      </tr>
      <tr>
        <td style="padding: 8px 0; color: #718096; font-size: 14px;">Exit Code:</td>
        <td style="padding: 8px 0; color: #2d3748; font-size: 14px;">{issue.exit_code if issue.exit_code is not None else 'N/A'}</td>
      </tr>
      <tr>
        <td style="padding: 8px 0; color: #718096; font-size: 14px;">Detected At:</td>
        <td style="padding: 8px 0; color: #2d3748; font-size: 14px;">{date_str}</td>
      </tr>
    </table>

    <div style="background: #fffaf0; border-left: 4px solid #dd6b20; padding: 12px; margin-bottom: 20px; border-radius: 4px;">
      <p style="margin: 0; color: #7b341e; font-size: 13px; line-height: 1.5;">
        <strong>Details:</strong> {html.escape(issue.message)}
      </p>
    </div>

    {logs_section}

    <div style="border-top: 1px solid #edf2f7; padding-top: 16px; margin-top: 24px; text-align: center; color: #a0aec0; font-size: 12px;">
      KubeAlert Cloud-Native Kubernetes Monitor • <a href="https://github.com/krycha1248/KubeAlert" style="color: #4299e1; text-decoration: none;">GitHub</a>
    </div>

  </div>
</body>
</html>
"""
