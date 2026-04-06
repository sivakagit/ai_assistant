"""
plugins/gmail_plugin.py  — Example plugin skeleton for Gmail integration.
Uses smtplib with Gmail App Password (no OAuth needed).
"""

PLUGIN_NAME    = "gmail"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR  = "Nova AI"
PLUGIN_DESC    = "Send emails via Gmail"
PLUGIN_INTENTS = ["send_email", "send_gmail", "email"]

import os
import re
import smtplib
from email.mime.text import MIMEText

GMAIL_USER     = os.getenv("GMAIL_USER", "")      # your@gmail.com
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")  # 16-char app password


def _parse(text: str):
    """
    Parse: 'email to someone@example.com subject Hello body Hi there'
    Returns (to, subject, body) or raises ValueError.
    """
    to_match  = re.search(r'\bto\s+([\w.@+\-]+)', text, re.IGNORECASE)
    sub_match = re.search(r'\bsubject\s+(.+?)(?:\s+body\s+|\s*$)', text, re.IGNORECASE)
    bod_match = re.search(r'\bbody\s+(.+)', text, re.IGNORECASE)

    if not to_match:
        raise ValueError("No recipient found. Use: email to someone@example.com subject ... body ...")

    return (
        to_match.group(1),
        sub_match.group(1).strip() if sub_match else "(no subject)",
        bod_match.group(1).strip() if bod_match else "",
    )


def handle(text: str) -> str:
    if not GMAIL_USER or not GMAIL_APP_PASS:
        return (
            "⚠️ Gmail not configured.\n"
            "Set GMAIL_USER and GMAIL_APP_PASS in your environment variables.\n"
            "Create an App Password at: https://myaccount.google.com/apppasswords"
        )

    try:
        to, subject, body = _parse(text)
    except ValueError as e:
        return f"⚠️ {e}"

    try:
        msg            = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = to

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_USER, to, msg.as_string())

        return f"✅ Email sent to {to}\nSubject: {subject}"
    except Exception as e:
        return f"⚠️ Gmail plugin error: {e}"
