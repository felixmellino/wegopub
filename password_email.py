"""Server-only Brevo delivery; never log the API key or reset code."""
import json
import os
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def email_settings():
    settings = {key: os.environ.get(key) for key in (
        "BREVO_API_KEY", "BREVO_SENDER_EMAIL", "BREVO_SENDER_NAME")}
    try:
        import streamlit as st
        for key in settings:
            settings[key] = st.secrets.get(key) or settings[key]
    except FileNotFoundError:
        pass
    if not settings["BREVO_API_KEY"] or not settings["BREVO_SENDER_EMAIL"]:
        raise RuntimeError("Password recovery is temporarily unavailable. Please try again later.")
    return settings


def reset_email(code):
    text = (
        "WeGoPub — Reset your password\n\n"
        "We received a request to reset your WeGoPub password.\n\n"
        f"Your reset code: {code}\n\n"
        "Enter this code in Forgot password in the WeGoPub app, then choose a new password.\n"
        "This code expires in 15 minutes and can only be used once.\n\n"
        "If you did not request this, ignore this email. Your password has not changed.\n"
        "Never share this code with anyone.\n\nThe WeGoPub team"
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#172b26;padding:24px">'
        '<h1 style="font-size:24px">WeGoPub</h1><h2>Reset your password</h2>'
        '<p>We received a request to reset your WeGoPub password.</p>'
        '<p>Your reset code:</p>'
        f'<p style="font-size:24px;font-weight:bold;letter-spacing:2px;background:#edf5f0;padding:16px">{escape(code)}</p>'
        '<p>Enter this code in <strong>Forgot password</strong> in the WeGoPub app, then choose a new password.</p>'
        '<p>This code expires in <strong>15 minutes</strong> and can only be used once.</p>'
        '<p>If you did not request this, ignore this email. Your password has not changed.</p>'
        '<p>Never share this code with anyone.</p><p>The WeGoPub team</p></div>'
    )
    return {"subject": "WeGoPub — Reset your password", "textContent": text, "htmlContent": html}


def send_reset_email(email, code, settings):
    payload = reset_email(code)
    payload.update(sender={"email": settings["BREVO_SENDER_EMAIL"],
                           "name": settings.get("BREVO_SENDER_NAME") or "WeGoPub"},
                   to=[{"email": email}])
    request = Request("https://api.brevo.com/v3/smtp/email",
                      data=json.dumps(payload).encode(), method="POST",
                      headers={"api-key": settings["BREVO_API_KEY"], "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            if response.status != 201:
                raise RuntimeError("Email delivery failed.")
    except (HTTPError, URLError, TimeoutError, OSError):
        # Brevo's body may contain recipient information; never display it.
        raise RuntimeError("Email delivery failed.") from None
