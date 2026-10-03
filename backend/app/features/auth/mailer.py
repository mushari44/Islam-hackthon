"""Sends account emails (password reset codes) over SMTP, standard library only. Owner: Eman.

Configure in .env: SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
Without SMTP_HOST, email is switched off and seekers reset with their recovery code instead.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from ...core.config import settings  # noqa: F401  (loads .env)

log = logging.getLogger("sabeeli.mail")


def enabled() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def send(to: str, subject: str, body: str) -> bool:
    if not enabled():
        return False
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER", "")
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(os.getenv("SMTP_HOST", ""), int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.getenv("SMTP_USER"):
                smtp.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as err:   # never let mail trouble break the request
        log.warning("email to a seeker failed: %s", type(err).__name__)
        return False
