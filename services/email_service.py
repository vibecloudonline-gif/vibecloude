"""services/email_service.py — Confirmación de cuenta por mail (opcional).

Sin SMTP_HOST configurada, el signup sigue funcionando exactamente como
antes (cuenta activa al toque, sin paso de confirmación) -- mismo patrón
que GODADDY_API_KEY/ANTHROPIC_API_KEY en el resto del proyecto: se puede
construir y probar sin credenciales reales, y el dueño activa el modo
cargando la variable en Render cuando quiera.

El link de confirmación usa un token firmado (itsdangerous, ya es
dependencia del proyecto para las cookies de sesión) en vez de una tabla
nueva en la DB -- el token en sí mismo prueba que es válido (firma +
vencimiento) y trae el user_id adentro.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core.config import settings as app_settings

EMAIL_CONFIRM_SALT = "vibecloud-email-confirm"
EMAIL_CONFIRM_MAX_AGE = 60 * 60 * 24  # 24 horas


class EmailServiceError(Exception):
    pass


def is_email_confirmation_enabled() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def generate_confirm_token(user_id: int) -> str:
    serializer = URLSafeTimedSerializer(app_settings.SECRET_KEY, salt=EMAIL_CONFIRM_SALT)
    return serializer.dumps({"user_id": user_id})


def verify_confirm_token(token: str, max_age: int = EMAIL_CONFIRM_MAX_AGE) -> Optional[int]:
    """Devuelve el user_id si el token es válido y no venció, None si no."""
    serializer = URLSafeTimedSerializer(app_settings.SECRET_KEY, salt=EMAIL_CONFIRM_SALT)
    try:
        data = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


def send_confirmation_email(to_email: str, confirm_url: str, empresa: str) -> None:
    host = os.getenv("SMTP_HOST", "")
    if not host:
        raise EmailServiceError("SMTP_HOST no configurada")

    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("EMAIL_FROM", user or "no-reply@vibecloud.online")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Confirmá tu cuenta de {empresa} en VibeCloud"
    msg["From"] = from_addr
    msg["To"] = to_email

    text = f"Confirmá tu cuenta entrando a este link (vence en 24hs):\n{confirm_url}"
    html = f"""
    <p>Confirmá tu cuenta de <strong>{empresa}</strong> en VibeCloud entrando a este link:</p>
    <p><a href="{confirm_url}">{confirm_url}</a></p>
    <p style="color:#6b7280; font-size:0.85em;">Este link vence en 24 horas.</p>
    """
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_string())
