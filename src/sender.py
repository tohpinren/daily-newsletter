"""SMTP email sender."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_newsletter_email(
    *,
    gmail_address: str,
    gmail_app_password: str,
    recipient_email: str,
    subject: str,
    html_body: str,
) -> None:
    """Send newsletter email via Gmail SMTP over TLS."""
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = gmail_address
    message["To"] = recipient_email
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(host="smtp.gmail.com", port=587, timeout=30) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.sendmail(gmail_address, [recipient_email], message.as_string())
