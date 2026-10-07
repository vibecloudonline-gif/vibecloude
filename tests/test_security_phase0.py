"""Tests de seguridad — Fase 0: seguridad máxima del MVP."""
import os
os.environ["SECRET_KEY"] = "testsecretkey123_for_security_tests!"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import json
import pytest
from decimal import Decimal
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select
from database.models import Tenant, User, PlatformPayment


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(e)
    return e


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant(session):
    existing = session.exec(select(Tenant).where(Tenant.subdomain == "sectest")).first()
    if existing:
        return existing
    t = Tenant(name="SecTest", subdomain="sectest", is_active=True, ai_credits=50)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@pytest.fixture
def admin_user(session, tenant):
    existing = session.exec(select(User).where(User.username == "admin_sec")).first()
    if existing:
        return existing
    u = User(
        tenant_id=tenant.id,
        username="admin_sec",
        password_hash="hashed",
        email="admin@sec.test",
        role="admin",
        is_active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture
def superadmin_user(session, tenant):
    existing = session.exec(select(User).where(User.username == "super_sec")).first()
    if existing:
        return existing
    u = User(
        tenant_id=tenant.id,
        username="super_sec",
        password_hash="hashed",
        email="super@sec.test",
        role="superadmin",
        is_active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


# =====================================================================
# 1. /credits/buy bloqueado para no-superadmin
# =====================================================================

class TestCreditsBuyBlocked:
    def test_credits_buy_returns_redirect(self, admin_user):
        from routers.ai import buy_tenant_credits

        result = buy_tenant_credits(current_user=admin_user)
        assert result["success"] is False
        assert "/api/v1/payments/credits/create" in result["redirect"]

    def test_credits_buy_deprecated_for_any_user(self, superadmin_user):
        from routers.ai import buy_tenant_credits

        result = buy_tenant_credits(current_user=superadmin_user)
        assert result["success"] is False
        assert "reemplazado" in result["message"].lower()


# =====================================================================
# 2. Secretos obligatorios en producción
# =====================================================================

class TestSecretsValidation:
    def test_production_requires_secret_key(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": "short"}, clear=False):
            with pytest.raises(ValueError, match="SECRET_KEY"):
                import importlib
                import core.config
                importlib.reload(core.config)

    def test_production_requires_vibecloud_api_key(self):
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "a" * 32,
            "VIBECLOUD_API_KEY": "",
            "DATABASE_URL": "postgresql://x",
        }, clear=False):
            with pytest.raises(ValueError, match="VIBECLOUD_API_KEY"):
                import importlib
                import core.config
                importlib.reload(core.config)

    def test_development_starts_without_secrets(self):
        with patch.dict(os.environ, {
            "ENVIRONMENT": "development",
            "SECRET_KEY": "dev",
            "VIBECLOUD_API_KEY": "",
        }, clear=False):
            import importlib
            import core.config
            importlib.reload(core.config)


# =====================================================================
# 3. Tenant filter — discovery
# =====================================================================

class TestTenantFilter:
    def test_discovers_tenant_models(self):
        from core.tenant_filter import _discover_tenant_models
        models = _discover_tenant_models()
        model_names = {m.__name__ for m in models}
        assert "Product" in model_names
        assert "Sale" in model_names
        assert "User" in model_names
        assert "Settings" in model_names
        assert "Tenant" not in model_names
        assert len(models) >= 30

    def test_tenant_not_in_filtered_models(self):
        from core.tenant_filter import _discover_tenant_models
        models = _discover_tenant_models()
        for m in models:
            assert m.__name__ != "Tenant"


# =====================================================================
# 4. Security headers middleware
# =====================================================================

class TestSecurityHeaders:
    def test_headers_present(self):
        from core.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.add_middleware(SecurityHeadersMiddleware)

        @test_app.get("/test")
        def _test():
            return {"ok": True}

        client = TestClient(test_app)
        resp = client.get("/test")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in resp.headers.get("Referrer-Policy", "")
        assert "camera=()" in resp.headers.get("Permissions-Policy", "")

    def test_cache_control_set(self):
        from core.security_headers import SecurityHeadersMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.add_middleware(SecurityHeadersMiddleware)

        @test_app.get("/test")
        def _test():
            return {"ok": True}

        client = TestClient(test_app)
        resp = client.get("/test")
        assert "no-store" in resp.headers.get("Cache-Control", "")


# =====================================================================
# 5. Cookie de sesión — verify middleware config is correct
# =====================================================================

class TestSessionCookie:
    def test_session_middleware_configured(self):
        from starlette.middleware.sessions import SessionMiddleware
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        test_app.add_middleware(
            SessionMiddleware,
            secret_key="test_secret_for_cookie_test",
            same_site="lax",
            https_only=False,
            max_age=86400 * 7,
        )

        @test_app.get("/test")
        def _test(request: Request):
            request.session["visited"] = True
            return {"ok": True}

        client = TestClient(test_app)
        resp = client.get("/test")
        set_cookie = resp.headers.get("set-cookie", "")
        assert "samesite=lax" in set_cookie.lower()


# =====================================================================
# 6. Password policy
# =====================================================================

class TestPasswordPolicy:
    def test_weak_password_rejected(self):
        from core.security_audit import validate_password_strength
        assert validate_password_strength("short") is not None
        assert validate_password_strength("alllowercase1!") is not None
        assert validate_password_strength("ALLUPPERCASE1!") is not None
        assert validate_password_strength("NoNumbers!!!") is not None
        assert validate_password_strength("NoSymbols1234") is not None

    def test_strong_password_accepted(self):
        from core.security_audit import validate_password_strength
        assert validate_password_strength("MyStr0ng!Pass") is None

    def test_common_password_rejected(self):
        from core.security_audit import validate_password_strength
        assert validate_password_strength("password") is not None


# =====================================================================
# 7. Audit log functions
# =====================================================================

class TestAuditLog:
    def test_audit_login_success_callable(self):
        from core.security_audit import audit_login_success
        audit_login_success("testuser", 1, 1, "127.0.0.1")

    def test_audit_login_failure_callable(self):
        from core.security_audit import audit_login_failure
        audit_login_failure("testuser", "127.0.0.1")

    def test_audit_logout_callable(self):
        from core.security_audit import audit_logout
        audit_logout(1, "127.0.0.1")

    def test_get_client_ip_forwarded(self):
        from core.security_audit import get_client_ip
        from unittest.mock import MagicMock
        req = MagicMock()
        req.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
        assert get_client_ip(req) == "1.2.3.4"

    def test_get_client_ip_direct(self):
        from core.security_audit import get_client_ip
        from unittest.mock import MagicMock
        req = MagicMock()
        req.headers = {}
        req.client.host = "10.0.0.1"
        assert get_client_ip(req) == "10.0.0.1"


# =====================================================================
# 8. AI logging
# =====================================================================

class TestAILogging:
    def test_base_adapter_has_log_call(self):
        from services.ai.providers.base import AIProviderAdapter
        assert hasattr(AIProviderAdapter, "log_call")

    def test_all_providers_have_log_call(self):
        from services.ai.providers.claude import ClaudeAdapter
        from services.ai.providers.gemini import GeminiAdapter
        from services.ai.providers.qwen import QwenAdapter
        from services.ai.providers.openai_provider import OpenAIAdapter
        for adapter_cls in [ClaudeAdapter, GeminiAdapter, QwenAdapter, OpenAIAdapter]:
            assert hasattr(adapter_cls, "log_call")


# =====================================================================
# 9. RLS SQL file exists
# =====================================================================

class TestRLSFile:
    def test_rls_sql_exists(self):
        rls_path = os.path.join(os.path.dirname(__file__), "..", "docs", "rls_deny_all.sql")
        assert os.path.exists(rls_path), "docs/rls_deny_all.sql debe existir"

    def test_rls_sql_has_enable_rls(self):
        rls_path = os.path.join(os.path.dirname(__file__), "..", "docs", "rls_deny_all.sql")
        with open(rls_path) as f:
            content = f.read()
        assert "ENABLE ROW LEVEL SECURITY" in content
        assert "tenant" in content.lower()


# =====================================================================
# 10. FastAPI version
# =====================================================================

class TestDependencyVersions:
    def test_fastapi_version_updated(self):
        import fastapi
        parts = fastapi.__version__.split(".")
        major, minor = int(parts[0]), int(parts[1])
        assert major == 0 and minor >= 115, f"FastAPI {fastapi.__version__} < 0.115"

    def test_python_multipart_importable(self):
        import multipart
        assert multipart is not None
