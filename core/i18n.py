"""core/i18n.py — Textos centralizados de la interfaz.

Base: español mexicano. Estructura preparada para agregar inglés después.
Uso: from core.i18n import t; t("auth.login_failed")
"""
from __future__ import annotations

_LANG = "es"

_TEXTS: dict[str, dict[str, str]] = {
    "es": {
        # ---------- Auth ----------
        "auth.login_failed": "Usuario o contraseña incorrectos.",
        "auth.login_rate_limited": "Demasiados intentos. Esperá unos minutos.",
        "auth.session_expired": "Tu sesión expiró. Iniciá sesión de nuevo.",
        "auth.forbidden": "No tenés permiso para acceder aquí.",
        "auth.admin_required": "Se requiere rol de administrador.",
        "auth.superadmin_required": "Se requiere rol de superadmin.",

        # ---------- Tenant / Entitlements ----------
        "tenant.not_found": "Tenant no encontrado.",
        "tenant.inactive": "Esta cuenta está desactivada.",
        "module.blocked": "Este módulo no está disponible en tu plan actual.",
        "module.upgrade_hint": "Se habilita cuando subas de nivel.",

        # ---------- Products ----------
        "product.not_found": "Producto no encontrado.",
        "product.import_success": "{count} productos importados correctamente.",
        "product.import_errors": "Se encontraron {count} errores al importar.",
        "product.barcode_exists": "Ya existe un producto con ese código de barras.",
        "product.name_required": "El nombre del producto es obligatorio.",

        # ---------- Sales / POS ----------
        "sale.empty_cart": "El carrito está vacío.",
        "sale.not_found": "Venta no encontrada.",
        "sale.insufficient_stock": "Stock insuficiente para {product}.",
        "sale.completed": "Venta registrada correctamente.",
        "sale.cancelled": "Venta anulada.",

        # ---------- Clients ----------
        "client.not_found": "Cliente no encontrado.",
        "client.payment_positive": "El monto del pago debe ser mayor a cero.",
        "client.import_success": "{count} clientes importados.",

        # ---------- Cash / Caja ----------
        "cash.no_open_session": "No hay sesión de caja abierta.",
        "cash.already_open": "Ya hay una sesión de caja abierta.",
        "cash.closed": "Caja cerrada correctamente.",

        # ---------- Stock / WMS ----------
        "stock.location_not_found": "Ubicación no encontrada.",
        "stock.bin_not_found": "Contenedor no encontrado.",
        "stock.insufficient": "Stock insuficiente.",
        "stock.transfer_ok": "Transferencia realizada.",

        # ---------- AI ----------
        "ai.not_enabled": "El módulo de IA no está habilitado para tu cuenta.",
        "ai.no_credits": "No tenés créditos de IA suficientes.",
        "ai.rate_limited": "Demasiadas solicitudes de IA. Esperá un momento.",
        "ai.generation_failed": "No se pudo generar el contenido. Intentá de nuevo.",

        # ---------- Landing ----------
        "landing.limit_reached": "Alcanzaste el límite de regeneraciones de landing para tu plan.",
        "landing.generated": "Landing generada correctamente.",

        # ---------- Storefront ----------
        "store.cart_empty": "Tu carrito está vacío.",
        "store.checkout_no_payment": "No hay pasarela de pago configurada.",
        "store.order_placed": "¡Pedido realizado! Te contactaremos pronto.",

        # ---------- Domains ----------
        "domain.invalid": "Dominio inválido.",
        "domain.already_registered": "Ese dominio ya está registrado en la plataforma.",
        "domain.requested": "Solicitud de dominio enviada.",

        # ---------- General ----------
        "general.save_ok": "Guardado correctamente.",
        "general.delete_ok": "Eliminado correctamente.",
        "general.invalid_input": "Datos inválidos.",
        "general.server_error": "Error interno. Intentá de nuevo.",
        "general.not_found": "No encontrado.",
    },
    "en": {
        "auth.login_failed": "Invalid username or password.",
        "auth.login_rate_limited": "Too many attempts. Wait a few minutes.",
        "auth.session_expired": "Your session expired. Please log in again.",
        "auth.forbidden": "You don't have permission to access this.",
        "auth.admin_required": "Administrator role required.",
        "auth.superadmin_required": "Superadmin role required.",

        "tenant.not_found": "Tenant not found.",
        "tenant.inactive": "This account is deactivated.",
        "module.blocked": "This module is not available on your current plan.",
        "module.upgrade_hint": "Available when you upgrade.",

        "product.not_found": "Product not found.",
        "product.import_success": "{count} products imported successfully.",
        "product.import_errors": "Found {count} errors during import.",
        "product.barcode_exists": "A product with that barcode already exists.",
        "product.name_required": "Product name is required.",

        "sale.empty_cart": "The cart is empty.",
        "sale.not_found": "Sale not found.",
        "sale.insufficient_stock": "Insufficient stock for {product}.",
        "sale.completed": "Sale registered successfully.",
        "sale.cancelled": "Sale cancelled.",

        "client.not_found": "Client not found.",
        "client.payment_positive": "Payment amount must be greater than zero.",
        "client.import_success": "{count} clients imported.",

        "cash.no_open_session": "No open cash session.",
        "cash.already_open": "There is already an open cash session.",
        "cash.closed": "Cash session closed successfully.",

        "stock.location_not_found": "Location not found.",
        "stock.bin_not_found": "Bin not found.",
        "stock.insufficient": "Insufficient stock.",
        "stock.transfer_ok": "Transfer completed.",

        "ai.not_enabled": "The AI module is not enabled for your account.",
        "ai.no_credits": "Not enough AI credits.",
        "ai.rate_limited": "Too many AI requests. Wait a moment.",
        "ai.generation_failed": "Could not generate content. Try again.",

        "landing.limit_reached": "You've reached the landing regeneration limit for your plan.",
        "landing.generated": "Landing generated successfully.",

        "store.cart_empty": "Your cart is empty.",
        "store.checkout_no_payment": "No payment gateway configured.",
        "store.order_placed": "Order placed! We'll contact you soon.",

        "domain.invalid": "Invalid domain.",
        "domain.already_registered": "That domain is already registered on the platform.",
        "domain.requested": "Domain request submitted.",

        "general.save_ok": "Saved successfully.",
        "general.delete_ok": "Deleted successfully.",
        "general.invalid_input": "Invalid input.",
        "general.server_error": "Internal error. Try again.",
        "general.not_found": "Not found.",
    },
}


def set_lang(lang: str) -> None:
    global _LANG
    if lang in _TEXTS:
        _LANG = lang


def t(key: str, lang: str | None = None, **kwargs: object) -> str:
    """Look up a translated string. Supports {placeholder} interpolation."""
    lang = lang or _LANG
    texts = _TEXTS.get(lang, _TEXTS["es"])
    text = texts.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
