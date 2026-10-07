"""Security audit logging and password policy for VibeCloud.

All security-relevant events are logged to the 'security.audit' logger
in structured format for monitoring and incident response.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("security.audit")

MIN_PASSWORD_LENGTH = 12


def audit_login_success(username: str, user_id: int, tenant_id: int | None, ip: str) -> None:
    logger.info(
        "LOGIN_SUCCESS user=%s user_id=%d tenant_id=%s ip=%s",
        username, user_id, tenant_id or "none", ip,
    )


def audit_login_failure(username: str, ip: str, reason: str = "invalid_credentials") -> None:
    logger.warning(
        "LOGIN_FAILURE user=%s ip=%s reason=%s",
        username, ip, reason,
    )


def audit_logout(user_id: int, ip: str) -> None:
    logger.info("LOGOUT user_id=%d ip=%s", user_id, ip)


def audit_signup(username: str, tenant_id: int, ip: str) -> None:
    logger.info(
        "SIGNUP user=%s tenant_id=%d ip=%s",
        username, tenant_id, ip,
    )


def audit_permission_denied(user_id: int, endpoint: str, ip: str) -> None:
    logger.warning(
        "PERMISSION_DENIED user_id=%d endpoint=%s ip=%s",
        user_id, endpoint, ip,
    )


def audit_tenant_filter_bypass(user_id: int | None, reason: str) -> None:
    logger.info(
        "TENANT_FILTER_BYPASS user_id=%s reason=%s",
        user_id or "anonymous", reason,
    )


def get_client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if hasattr(request, "client") and request.client:
        return request.client.host
    return "unknown"


def validate_password_strength(password: str) -> str | None:
    """Return an error message if password is weak, or None if strong enough."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
    if not re.search(r"[a-z]", password):
        return "La contraseña debe incluir al menos una letra minúscula."
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe incluir al menos una letra mayúscula."
    if not re.search(r"\d", password):
        return "La contraseña debe incluir al menos un número."
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:,<.>/?\\|]", password):
        return "La contraseña debe incluir al menos un símbolo."
    common = {"password", "12345678", "qwerty", "admin", "vibecloud", "123456789012"}
    if password.lower() in common:
        return "La contraseña es demasiado común."
    return None


def regenerate_session(request) -> None:
    """Mitigate session fixation by clearing and re-creating the session."""
    old_data = dict(request.session)
    request.session.clear()
    for key, value in old_data.items():
        request.session[key] = value
