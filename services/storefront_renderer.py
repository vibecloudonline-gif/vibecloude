"""services/storefront_renderer.py — Motor data-driven del storefront.

Arquitectura: SiteConfig (Pydantic) + Theme Presets + Block Registry + Renderer.
Jinja recibe datos estructurados, nunca variables sueltas.
La IA genera JSON validado contra estos schemas, nunca HTML/CSS crudo.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database.models import Settings

logger = logging.getLogger(__name__)


# ── Theme Tokens ──────────────────────────────────────────────────────────

class ThemeTokens(BaseModel):
    preset: str = "elegante"
    # Colors
    primary: str = "#0f172a"
    accent: str = "#c9a96e"
    background: str = "#fafaf9"
    surface: str = "#ffffff"
    surface_alt: str = "#f5f5f4"
    text: str = "#1a1a1a"
    text_muted: str = "#78716c"
    border: str = "rgba(0,0,0,0.08)"
    success: str = "#16a34a"
    danger: str = "#dc2626"
    # Typography
    heading_font: str = "Playfair Display"
    body_font: str = "Inter"
    heading_weight: str = "700"
    # Shape
    radius: str = "2px"
    radius_lg: str = "4px"
    card_radius: str = "4px"
    button_radius: str = "2px"
    # Shadows
    shadow_sm: str = "0 1px 2px rgba(0,0,0,0.05)"
    shadow_md: str = "0 4px 12px rgba(0,0,0,0.08)"
    shadow_lg: str = "0 8px 24px rgba(0,0,0,0.12)"
    # AlexIO bubble
    alexio_bg: str = "#0f172a"
    alexio_text: str = "#ffffff"


# ── Section Config ────────────────────────────────────────────────────────

class SectionConfig(BaseModel):
    type: str
    enabled: bool = True
    order: int = 0
    data: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)


# ── Navigation & Commerce ─────────────────────────────────────────────────

class NavigationConfig(BaseModel):
    header_style: str = "standard"
    show_search: bool = True
    show_cart: bool = True
    show_alexio: bool = True
    footer_columns: int = 1

class CommerceConfig(BaseModel):
    currency: str = "USD"
    currency_symbol: str = "$"
    show_stock: bool = False
    show_prices: bool = True
    product_card_variant: str = "standard"


# ── SiteConfig (single source of truth) ───────────────────────────────────

class SiteConfig(BaseModel):
    theme: ThemeTokens = Field(default_factory=ThemeTokens)
    sections: list[SectionConfig] = Field(default_factory=list)
    navigation: NavigationConfig = Field(default_factory=NavigationConfig)
    commerce: CommerceConfig = Field(default_factory=CommerceConfig)


# ── 4 Theme Presets ───────────────────────────────────────────────────────

THEME_PRESETS: dict[str, dict] = {
    "elegante": {
        "preset": "elegante",
        "primary": "#0f172a",
        "accent": "#c9a96e",
        "background": "#fafaf9",
        "surface": "#ffffff",
        "surface_alt": "#f5f5f4",
        "text": "#1a1a1a",
        "text_muted": "#78716c",
        "border": "rgba(0,0,0,0.06)",
        "success": "#16a34a",
        "danger": "#dc2626",
        "heading_font": "Playfair Display",
        "body_font": "Inter",
        "heading_weight": "700",
        "radius": "2px",
        "radius_lg": "4px",
        "card_radius": "4px",
        "button_radius": "2px",
        "shadow_sm": "0 1px 2px rgba(0,0,0,0.04)",
        "shadow_md": "0 4px 12px rgba(0,0,0,0.06)",
        "shadow_lg": "0 8px 24px rgba(0,0,0,0.1)",
        "alexio_bg": "#0f172a",
        "alexio_text": "#ffffff",
    },
    "urbano": {
        "preset": "urbano",
        "primary": "#ffffff",
        "accent": "#f97316",
        "background": "#0a0a0a",
        "surface": "#171717",
        "surface_alt": "#262626",
        "text": "#fafafa",
        "text_muted": "#a3a3a3",
        "border": "rgba(255,255,255,0.1)",
        "success": "#22c55e",
        "danger": "#ef4444",
        "heading_font": "Space Grotesk",
        "body_font": "Inter",
        "heading_weight": "700",
        "radius": "8px",
        "radius_lg": "12px",
        "card_radius": "12px",
        "button_radius": "8px",
        "shadow_sm": "0 1px 3px rgba(0,0,0,0.3)",
        "shadow_md": "0 4px 16px rgba(0,0,0,0.4)",
        "shadow_lg": "0 8px 32px rgba(0,0,0,0.5)",
        "alexio_bg": "#f97316",
        "alexio_text": "#ffffff",
    },
    "natural": {
        "preset": "natural",
        "primary": "#166534",
        "accent": "#ca8a04",
        "background": "#fefdf8",
        "surface": "#ffffff",
        "surface_alt": "#fef9ee",
        "text": "#292524",
        "text_muted": "#78716c",
        "border": "rgba(0,0,0,0.07)",
        "success": "#15803d",
        "danger": "#b91c1c",
        "heading_font": "Lora",
        "body_font": "Inter",
        "heading_weight": "600",
        "radius": "12px",
        "radius_lg": "16px",
        "card_radius": "16px",
        "button_radius": "999px",
        "shadow_sm": "0 1px 3px rgba(0,0,0,0.04)",
        "shadow_md": "0 4px 12px rgba(22,101,52,0.08)",
        "shadow_lg": "0 8px 24px rgba(22,101,52,0.12)",
        "alexio_bg": "#166534",
        "alexio_text": "#ffffff",
    },
    "tech": {
        "preset": "tech",
        "primary": "#818cf8",
        "accent": "#06b6d4",
        "background": "#030712",
        "surface": "#111827",
        "surface_alt": "#1f2937",
        "text": "#f9fafb",
        "text_muted": "#9ca3af",
        "border": "rgba(255,255,255,0.08)",
        "success": "#34d399",
        "danger": "#f87171",
        "heading_font": "JetBrains Mono",
        "body_font": "Inter",
        "heading_weight": "700",
        "radius": "6px",
        "radius_lg": "8px",
        "card_radius": "8px",
        "button_radius": "6px",
        "shadow_sm": "0 1px 3px rgba(0,0,0,0.4)",
        "shadow_md": "0 4px 16px rgba(6,182,212,0.1)",
        "shadow_lg": "0 8px 32px rgba(129,140,248,0.15)",
        "alexio_bg": "#818cf8",
        "alexio_text": "#ffffff",
    },
}


# ── Default sections per theme ────────────────────────────────────────────

DEFAULT_SECTIONS: dict[str, list[dict]] = {
    "elegante": [
        {"type": "hero", "order": 0, "data": {
            "title": "Bienvenido a nuestra tienda",
            "subtitle": "Productos seleccionados con cuidado para vos",
            "cta_text": "Ver catálogo",
            "cta_url": "#catalogo",
        }},
        {"type": "featured_products", "order": 1, "data": {
            "title": "Productos destacados",
            "max_items": 4,
        }},
        {"type": "product_grid", "order": 2, "data": {
            "title": "Todo el catálogo",
        }},
    ],
    "urbano": [
        {"type": "hero", "order": 0, "data": {
            "title": "Lo último está acá",
            "subtitle": "Encontrá lo que buscás",
            "cta_text": "Explorar",
            "cta_url": "#catalogo",
        }},
        {"type": "banner", "order": 1, "data": {
            "text": "Envío gratis en compras mayores a $5,000",
            "style": "accent",
        }},
        {"type": "product_grid", "order": 2, "data": {
            "title": "Productos",
        }},
    ],
    "natural": [
        {"type": "hero", "order": 0, "data": {
            "title": "Productos naturales, hechos con amor",
            "subtitle": "De la tierra a tu mesa",
            "cta_text": "Descubrir",
            "cta_url": "#catalogo",
        }},
        {"type": "features", "order": 1, "data": {
            "title": "¿Por qué elegirnos?",
            "items": [
                {"icon": "🌱", "title": "Natural", "desc": "Ingredientes de origen natural"},
                {"icon": "🤝", "title": "Artesanal", "desc": "Producción local y cuidada"},
                {"icon": "📦", "title": "Envíos", "desc": "Llegamos a todo el país"},
            ],
        }},
        {"type": "product_grid", "order": 2, "data": {
            "title": "Nuestros productos",
        }},
    ],
    "tech": [
        {"type": "hero", "order": 0, "data": {
            "title": "Tecnología que conecta",
            "subtitle": "Los mejores productos tech al mejor precio",
            "cta_text": "Ver productos",
            "cta_url": "#catalogo",
        }},
        {"type": "product_grid", "order": 1, "data": {
            "title": "Catálogo",
        }},
        {"type": "banner", "order": 2, "data": {
            "text": "Garantía extendida en todos los productos",
            "style": "primary",
        }},
    ],
}


BLOCK_TEMPLATES: dict[str, str] = {
    "hero": "blocks/hero.html",
    "featured_products": "blocks/featured_products.html",
    "product_grid": "blocks/product_grid.html",
    "category_grid": "blocks/category_grid.html",
    "banner": "blocks/banner.html",
    "features": "blocks/features.html",
    "newsletter": "blocks/newsletter.html",
}


# ── Renderer functions ────────────────────────────────────────────────────

def get_theme_preset(template_name: str) -> ThemeTokens:
    preset_data = THEME_PRESETS.get(template_name, THEME_PRESETS["elegante"])
    return ThemeTokens(**preset_data)


def render_theme_css(theme: ThemeTokens) -> str:
    """CSS custom properties block to inject in <style>."""
    fonts = set()
    for f in [theme.heading_font, theme.body_font]:
        if f and f != "Inter":
            fonts.add(f)

    font_imports = ""
    if fonts:
        families = "&".join(f"family={f.replace(' ', '+')}:wght@400;500;600;700" for f in sorted(fonts))
        font_imports = f'@import url("https://fonts.googleapis.com/css2?{families}&family=Inter:wght@400;500;600;700&display=swap");'
    else:
        font_imports = '@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap");'

    return f"""{font_imports}

:root {{
    --sf-primary: {theme.primary};
    --sf-accent: {theme.accent};
    --sf-bg: {theme.background};
    --sf-surface: {theme.surface};
    --sf-surface-alt: {theme.surface_alt};
    --sf-text: {theme.text};
    --sf-text-muted: {theme.text_muted};
    --sf-border: {theme.border};
    --sf-success: {theme.success};
    --sf-danger: {theme.danger};
    --sf-heading-font: '{theme.heading_font}', 'Inter', system-ui, sans-serif;
    --sf-body-font: '{theme.body_font}', system-ui, sans-serif;
    --sf-heading-weight: {theme.heading_weight};
    --sf-radius: {theme.radius};
    --sf-radius-lg: {theme.radius_lg};
    --sf-card-radius: {theme.card_radius};
    --sf-btn-radius: {theme.button_radius};
    --sf-shadow-sm: {theme.shadow_sm};
    --sf-shadow-md: {theme.shadow_md};
    --sf-shadow-lg: {theme.shadow_lg};
    --sf-alexio-bg: {theme.alexio_bg};
    --sf-alexio-text: {theme.alexio_text};
}}"""


def get_site_config(session: Session, tenant_id: int) -> SiteConfig:
    """Load SiteConfig from Settings.site_config_json, or build default from preset."""
    settings = session.exec(
        select(Settings).where(Settings.tenant_id == tenant_id)
    ).first()

    template_name = "elegante"
    if settings:
        template_name = settings.storefront_template or "elegante"

        if hasattr(settings, "site_config_json") and settings.site_config_json:
            try:
                data = json.loads(settings.site_config_json)
                return SiteConfig(**data)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Invalid site_config_json for tenant %s: %s", tenant_id, e)

    theme = get_theme_preset(template_name)
    default_sections = DEFAULT_SECTIONS.get(template_name, DEFAULT_SECTIONS["elegante"])
    sections = [SectionConfig(**s) for s in default_sections]

    return SiteConfig(theme=theme, sections=sections)


def get_storefront_context(
    session: Session,
    tenant_id: int,
    settings: Settings,
    products: list,
    cart_count: int,
    request: Any,
    **extra: Any,
) -> dict:
    """Build the full template context for any storefront page."""
    site_config = get_site_config(session, tenant_id)
    theme_css = render_theme_css(site_config.theme)

    enabled_sections = [
        s for s in site_config.sections if s.enabled
    ]
    enabled_sections.sort(key=lambda s: s.order)

    ctx = {
        "request": request,
        "settings": settings,
        "products": products,
        "cart_count": cart_count,
        "site_config": site_config,
        "theme_css": theme_css,
        "sections": enabled_sections,
        "navigation": site_config.navigation,
        "commerce": site_config.commerce,
        "theme": site_config.theme,
        "block_templates": BLOCK_TEMPLATES,
    }
    ctx.update(extra)
    return ctx
