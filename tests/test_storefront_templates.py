"""Tests para los 11 theme presets del storefront (4 genéricos + 7 por tipo de negocio)."""
import pytest

from services.storefront_renderer import (
    BLOCK_TEMPLATES,
    DEFAULT_SECTIONS,
    THEME_PRESETS,
    VALID_TEMPLATE_NAMES,
    SiteConfig,
    ThemeTokens,
    get_theme_preset,
    render_theme_css,
)


ALL_PRESET_NAMES = [
    "elegante", "urbano", "natural", "tech",
    "sabor", "vitrina", "aura", "impulso", "nido", "estudio", "mercado",
]


class TestThemePresets:
    def test_all_11_presets_exist(self):
        assert len(THEME_PRESETS) == 11
        for name in ALL_PRESET_NAMES:
            assert name in THEME_PRESETS, f"Preset '{name}' falta en THEME_PRESETS"

    def test_valid_template_names_matches(self):
        assert VALID_TEMPLATE_NAMES == frozenset(THEME_PRESETS.keys())

    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_preset_creates_valid_theme_tokens(self, name):
        theme = get_theme_preset(name)
        assert isinstance(theme, ThemeTokens)
        assert theme.preset == name
        assert theme.primary.startswith("#") or theme.primary.startswith("r")
        assert theme.heading_font
        assert theme.body_font

    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_preset_renders_css(self, name):
        theme = get_theme_preset(name)
        css = render_theme_css(theme)
        assert "--sf-primary:" in css
        assert "--sf-accent:" in css
        assert "--sf-heading-font:" in css
        assert "fonts.googleapis.com" in css

    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_preset_has_required_tokens(self, name):
        preset = THEME_PRESETS[name]
        required_keys = [
            "preset", "primary", "accent", "background", "surface",
            "text", "text_muted", "heading_font", "body_font",
            "radius", "card_radius", "button_radius",
            "shadow_sm", "shadow_md", "shadow_lg",
        ]
        for key in required_keys:
            assert key in preset, f"Preset '{name}' falta la key '{key}'"

    def test_fallback_to_elegante(self):
        theme = get_theme_preset("nonexistent")
        assert theme.preset == "elegante"


class TestDefaultSections:
    def test_all_presets_have_sections(self):
        for name in ALL_PRESET_NAMES:
            assert name in DEFAULT_SECTIONS, f"DEFAULT_SECTIONS falta '{name}'"

    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_sections_have_valid_block_types(self, name):
        for section in DEFAULT_SECTIONS[name]:
            assert section["type"] in BLOCK_TEMPLATES, (
                f"Sección '{section['type']}' del preset '{name}' "
                f"no está registrada en BLOCK_TEMPLATES"
            )

    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_sections_have_order(self, name):
        orders = [s["order"] for s in DEFAULT_SECTIONS[name]]
        assert orders == sorted(orders), f"Secciones de '{name}' no están en orden"

    def test_sabor_has_menu_grid(self):
        types = [s["type"] for s in DEFAULT_SECTIONS["sabor"]]
        assert "menu_grid" in types

    def test_aura_has_services_and_gallery(self):
        types = [s["type"] for s in DEFAULT_SECTIONS["aura"]]
        assert "services_list" in types
        assert "gallery" in types

    def test_estudio_has_services_and_testimonials(self):
        types = [s["type"] for s in DEFAULT_SECTIONS["estudio"]]
        assert "services_list" in types
        assert "testimonials" in types


class TestBlockTemplates:
    def test_12_block_templates_registered(self):
        assert len(BLOCK_TEMPLATES) == 12

    def test_new_blocks_registered(self):
        new_blocks = ["menu_grid", "services_list", "gallery", "testimonials", "contact_info"]
        for block in new_blocks:
            assert block in BLOCK_TEMPLATES


class TestSiteConfig:
    @pytest.mark.parametrize("name", ALL_PRESET_NAMES)
    def test_preset_builds_valid_site_config(self, name):
        from services.storefront_renderer import SectionConfig
        theme = get_theme_preset(name)
        sections = [SectionConfig(**s) for s in DEFAULT_SECTIONS[name]]
        config = SiteConfig(theme=theme, sections=sections)
        assert config.theme.preset == name
        assert len(config.sections) > 0


class TestSettingsValidation:
    def test_accepts_all_11_templates(self):
        for name in ALL_PRESET_NAMES:
            assert name in VALID_TEMPLATE_NAMES

    def test_rejects_invalid_template(self):
        assert "wordpress" not in VALID_TEMPLATE_NAMES
        assert "invalid" not in VALID_TEMPLATE_NAMES


class TestLandingUnification:
    def test_landing_service_accepts_storefront_template_param(self):
        import inspect
        from services.landing_service import generate_landing_content
        sig = inspect.signature(generate_landing_content)
        assert "storefront_template" in sig.parameters

    def test_cascade_accepts_storefront_template_param(self):
        import inspect
        from services.ai_gateway_service import AIGatewayService
        sig = inspect.signature(AIGatewayService.generate_landing_content_cascade)
        assert "storefront_template" in sig.parameters
