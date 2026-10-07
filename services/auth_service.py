import logging
import os
import secrets

import argon2
from sqlmodel import Session, select

from database.models import Settings, Tenant, User

logger = logging.getLogger("auth")

_argon2_hasher = argon2.PasswordHasher()

_bcrypt_fallback = None
try:
    import bcrypt as _bcrypt_mod
    _bcrypt_fallback = _bcrypt_mod
except ImportError:
    pass


def _verify_bcrypt_legacy(plain_password: str, hashed: str) -> bool:
    if _bcrypt_fallback is None:
        return False
    try:
        return _bcrypt_fallback.checkpw(
            plain_password.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except Exception:
        return False


def _get_secure_password(env_var: str, label: str) -> str:
    password = os.getenv(env_var)
    if password:
        return password
    generated = secrets.token_urlsafe(16)
    print(f"\n{'='*60}")
    print(f"SEGURIDAD: No se encontro {env_var} en variables de entorno.")
    print(f"Se genero una contrasena segura para '{label}':")
    print(f"{label}: {generated}")
    print(f"GUARDALA Y CONFIGURALA EN TUS VARIABLES DE ENTORNO")
    print(f"{'='*60}\n")
    return generated


class AuthService:
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        if hashed_password.startswith("$argon2"):
            try:
                result = _argon2_hasher.verify(hashed_password, plain_password)
                if result and _argon2_hasher.check_needs_rehash(hashed_password):
                    logger.info("Argon2 hash needs rehash (params updated)")
                return result
            except (argon2.exceptions.VerifyMismatchError, argon2.exceptions.VerificationError):
                return False

        if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
            ok = _verify_bcrypt_legacy(plain_password, hashed_password)
            if ok:
                logger.info("Verified bcrypt legacy hash — will rehash to argon2 on next save")
            return ok

        return False

    @staticmethod
    def get_password_hash(password: str) -> str:
        return _argon2_hasher.hash(password)

    @staticmethod
    def needs_rehash(hashed_password: str) -> bool:
        if not hashed_password.startswith("$argon2"):
            return True
        return _argon2_hasher.check_needs_rehash(hashed_password)

    @staticmethod
    def create_default_user_and_settings(session: Session):
        tenant = session.exec(select(Tenant).order_by(Tenant.id)).first()
        if not tenant:
            tenant = Tenant(name="Default Company", subdomain="default")
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
            print(f"INFO: Created default Tenant (ID: {tenant.id})")

        user = session.exec(select(User).where(User.username == "admin", User.tenant_id == tenant.id)).first()
        admin_env_pw = os.getenv("ADMIN_PASSWORD")
        if not user:
            default_password = _get_secure_password("ADMIN_PASSWORD", "admin")
            hashed = AuthService.get_password_hash(default_password)
            user = User(
                username="admin",
                password_hash=hashed,
                role="admin",
                full_name="Administrador",
                tenant_id=tenant.id,
            )
            session.add(user)
            print(f"INFO: Created default user 'admin' (Tenant: {tenant.id})")
        elif admin_env_pw:
            if not AuthService.verify_password(admin_env_pw, user.password_hash):
                user.password_hash = AuthService.get_password_hash(admin_env_pw)
                session.add(user)
                print("INFO: Admin password synced from ADMIN_PASSWORD env var")
            elif AuthService.needs_rehash(user.password_hash):
                user.password_hash = AuthService.get_password_hash(admin_env_pw)
                session.add(user)
                print("INFO: Admin password rehashed to argon2")

        superadmin = session.exec(select(User).where(User.username == "superadmin")).first()
        superadmin_env_pw = os.getenv("SUPERADMIN_PASSWORD")
        if not superadmin:
            default_password = _get_secure_password("SUPERADMIN_PASSWORD", "superadmin")
            hashed = AuthService.get_password_hash(default_password)
            superadmin = User(
                username="superadmin",
                password_hash=hashed,
                role="superadmin",
                full_name="Super Administrador Global",
                tenant_id=tenant.id,
            )
            session.add(superadmin)
            print("INFO: Created default user 'superadmin'")
        elif superadmin_env_pw:
            if not AuthService.verify_password(superadmin_env_pw, superadmin.password_hash):
                superadmin.password_hash = AuthService.get_password_hash(superadmin_env_pw)
                session.add(superadmin)
                print("INFO: Superadmin password synced from SUPERADMIN_PASSWORD env var")
            elif AuthService.needs_rehash(superadmin.password_hash):
                superadmin.password_hash = AuthService.get_password_hash(superadmin_env_pw)
                session.add(superadmin)
                print("INFO: Superadmin password rehashed to argon2")

        settings = session.exec(select(Settings).where(Settings.tenant_id == tenant.id)).first()
        if not settings:
            default_settings = Settings(
                tenant_id=tenant.id,
                company_name="VibeCloud",
                logo_url="/static/images/logo.png",
            )
            session.add(default_settings)
            print("INFO: Created default settings for Tenant")

        session.commit()
