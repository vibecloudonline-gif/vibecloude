"""Tests Fase 2 — Auth (argon2/bcrypt), i18n, Dockerfile."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123_phase2!")
os.environ.setdefault("VIBECLOUD_API_KEY", "test-key-phase2")

import pytest
from services.auth_service import AuthService


class TestArgon2Hashing:
    def test_hash_produces_argon2(self):
        h = AuthService.get_password_hash("MyPassword123!")
        assert h.startswith("$argon2")

    def test_verify_correct_password(self):
        h = AuthService.get_password_hash("SecurePass99")
        assert AuthService.verify_password("SecurePass99", h) is True

    def test_verify_wrong_password(self):
        h = AuthService.get_password_hash("SecurePass99")
        assert AuthService.verify_password("WrongPass", h) is False

    def test_verify_empty_password(self):
        h = AuthService.get_password_hash("RealPass")
        assert AuthService.verify_password("", h) is False

    def test_different_hashes_for_same_password(self):
        h1 = AuthService.get_password_hash("SamePassword")
        h2 = AuthService.get_password_hash("SamePassword")
        assert h1 != h2  # salt differs

    def test_both_verify(self):
        h1 = AuthService.get_password_hash("SamePassword")
        h2 = AuthService.get_password_hash("SamePassword")
        assert AuthService.verify_password("SamePassword", h1) is True
        assert AuthService.verify_password("SamePassword", h2) is True


class TestBcryptLegacy:
    def test_verify_bcrypt_hash(self):
        try:
            import bcrypt
        except ImportError:
            pytest.skip("bcrypt not installed")
        legacy_hash = bcrypt.hashpw(b"OldPassword1", bcrypt.gensalt()).decode("utf-8")
        assert legacy_hash.startswith("$2b$")
        assert AuthService.verify_password("OldPassword1", legacy_hash) is True
        assert AuthService.verify_password("Wrong", legacy_hash) is False

    def test_bcrypt_needs_rehash(self):
        try:
            import bcrypt
        except ImportError:
            pytest.skip("bcrypt not installed")
        legacy_hash = bcrypt.hashpw(b"Test123", bcrypt.gensalt()).decode("utf-8")
        assert AuthService.needs_rehash(legacy_hash) is True

    def test_argon2_no_rehash_needed(self):
        h = AuthService.get_password_hash("Fresh")
        assert AuthService.needs_rehash(h) is False


class TestUnknownHash:
    def test_unknown_hash_format_rejected(self):
        assert AuthService.verify_password("pass", "plaintext_not_a_hash") is False

    def test_empty_hash_rejected(self):
        assert AuthService.verify_password("pass", "") is False


class TestI18n:
    def test_t_returns_spanish_by_default(self):
        from core.i18n import t
        assert t("tenant.not_found") == "Tenant no encontrado."

    def test_t_returns_english(self):
        from core.i18n import t
        assert t("tenant.not_found", lang="en") == "Tenant not found."

    def test_t_interpolation(self):
        from core.i18n import t
        result = t("product.import_success", count=42)
        assert "42" in result

    def test_t_missing_key_returns_key(self):
        from core.i18n import t
        assert t("nonexistent.key") == "nonexistent.key"

    def test_t_english_interpolation(self):
        from core.i18n import t
        result = t("sale.insufficient_stock", lang="en", product="Widget")
        assert "Widget" in result

    def test_set_lang(self):
        from core.i18n import set_lang, t, _LANG
        original = _LANG
        set_lang("en")
        assert t("general.save_ok") == "Saved successfully."
        set_lang("es")
        assert t("general.save_ok") == "Guardado correctamente."
        set_lang(original)

    def test_set_lang_invalid_ignored(self):
        from core.i18n import set_lang, t, _LANG
        original = _LANG
        set_lang("fr")  # not in _TEXTS
        assert t("tenant.not_found") != ""  # still works with fallback
        set_lang(original)


class TestDockerfile:
    def test_dockerfile_exists(self):
        dockerfile = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")
        assert os.path.exists(dockerfile)

    def test_dockerfile_has_proxy_headers(self):
        dockerfile = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")
        content = open(dockerfile).read()
        assert "--proxy-headers" in content

    def test_dockerfile_uses_port_env(self):
        dockerfile = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")
        content = open(dockerfile).read()
        assert "PORT" in content

    def test_dockerfile_has_nonroot_user(self):
        dockerfile = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")
        content = open(dockerfile).read()
        assert "USER" in content
        assert "appuser" in content


class TestCIWorkflow:
    def test_ci_yml_exists(self):
        ci = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "ci.yml")
        assert os.path.exists(ci)

    def test_ci_has_postgres(self):
        ci = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "ci.yml")
        content = open(ci).read()
        assert "postgres:15" in content

    def test_ci_runs_alembic(self):
        ci = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "ci.yml")
        content = open(ci).read()
        assert "alembic upgrade head" in content

    def test_ci_runs_ruff(self):
        ci = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "ci.yml")
        content = open(ci).read()
        assert "ruff check" in content

    def test_ci_deploy_only_on_main(self):
        ci = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "ci.yml")
        content = open(ci).read()
        assert "refs/heads/main" in content

    def test_ruff_config_exists(self):
        ruff_toml = os.path.join(os.path.dirname(__file__), "..", "ruff.toml")
        assert os.path.exists(ruff_toml)
