"""routers/storefront.py — Ecommerce público (Fase 2 del roadmap).

Server-rendered (Jinja) sobre el mismo backend, sin frontend separado, tal
como se decidió. Todo el tenant se resuelve por dominio (get_public_tenant) —
ningún endpoint de esta tienda acepta tenant_id como parámetro de request.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from database.models import Product, Sale, Settings, Tenant, TenantCatalog
from database.session import get_session
from services.ai_brain_service import ai_brain_service
from services.ai_gateway_service import ai_gateway_service
from services.storefront_order_service import StorefrontOrderError, create_order
from web.compat_templates import CompatTemplates
from web.dependencies import get_public_tenant

router = APIRouter(tags=["Storefront"])

# AlexIO Live en el storefront público solo puede consultar catálogo/stock --
# nunca metricas de ventas (dato de negocio, no debe verlo un visitante
# anónimo). Ver services/ai_brain_service.py::chat_response(allowed_tools=).
ALEXIO_LIVE_ALLOWED_TOOLS = ["consultar_stock", "recomendar_productos"]
ALEXIO_LIVE_SYSTEM_PROMPT = (
    "Sos AlexIO, el asistente virtual de la tienda. Ayudás a los visitantes a encontrar "
    "productos y responder dudas de stock. Tono cercano y breve, en español. "
    "No inventes precios ni stock -- usá siempre las herramientas para consultar datos reales. "
    "No tenés acceso a ventas ni facturación, si te preguntan por eso decí que no podés compartir esa información."
)


def _templates():
    return CompatTemplates(directory="templates")


def _get_store_settings(session: Session, tenant_id: int) -> Settings:
    settings = session.exec(select(Settings).where(Settings.tenant_id == tenant_id)).first()
    if not settings:
        settings = Settings(tenant_id=tenant_id, company_name="Tienda")
    return settings


def _get_cart(request: Request) -> dict:
    return request.session.get("cart", {})


def _save_cart(request: Request, cart: dict) -> None:
    request.session["cart"] = cart


def _cart_products(session: Session, tenant_id: int, cart: dict) -> list[dict]:
    if not cart:
        return []
    product_ids = [int(pid) for pid in cart.keys()]
    products = session.exec(
        select(Product).where(Product.id.in_(product_ids), Product.tenant_id == tenant_id)
    ).all()
    products_by_id = {p.id: p for p in products}

    lines = []
    for pid_str, qty in cart.items():
        product = products_by_id.get(int(pid_str))
        if not product:
            continue
        unit_price = product.price_retail or product.price
        lines.append({
            "product": product,
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": unit_price * qty,
        })
    return lines


@router.get("/tienda", response_class=HTMLResponse)
def storefront_catalog(
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    settings = _get_store_settings(session, tenant_id)

    curated_ids = session.exec(
        select(TenantCatalog.product_id).where(TenantCatalog.tenant_id == tenant_id)
    ).all()
    query = select(Product).where(Product.tenant_id == tenant_id, Product.is_deleted == False)
    if curated_ids:
        query = query.where(Product.id.in_(curated_ids))
    products = session.exec(query).all()

    cart = _get_cart(request)
    cart_count = sum(cart.values()) if cart else 0

    return _templates().TemplateResponse(
        "storefront_catalog.html",
        {"request": request, "settings": settings, "products": products, "cart_count": cart_count},
    )


@router.get("/tienda/producto/{product_id}", response_class=HTMLResponse)
def storefront_product_detail(
    product_id: int,
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    settings = _get_store_settings(session, tenant_id)
    product = session.exec(
        select(Product).where(
            Product.id == product_id, Product.tenant_id == tenant_id, Product.is_deleted == False
        )
    ).first()
    if not product:
        return _templates().TemplateResponse(
            "storefront_catalog.html",
            {"request": request, "settings": settings, "products": [], "cart_count": 0, "error": "Producto no encontrado"},
            status_code=404,
        )

    cart = _get_cart(request)
    cart_count = sum(cart.values()) if cart else 0

    return _templates().TemplateResponse(
        "storefront_product.html",
        {"request": request, "settings": settings, "product": product, "cart_count": cart_count},
    )


def _serialize_recommendation(product: Product) -> dict:
    price = product.price_retail or product.price
    return {
        "id": product.id,
        "name": product.name,
        "price": float(price) if price is not None else None,
        "image_url": product.image_url,
    }


@router.get("/tienda/producto/{product_id}/recomendados")
async def storefront_product_recommendations(
    product_id: int,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    """Recomendación predictiva (Qwen, actualización 2026-08-11) para un producto puntual."""
    recommended = await ai_gateway_service.recommend_products(
        session, tenant_id, seed_product_ids=[product_id]
    )
    return {"recommended": [_serialize_recommendation(p) for p in recommended]}


@router.get("/tienda/carrito/recomendados")
async def storefront_cart_recommendations(
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    """Recomendación predictiva (Qwen, actualización 2026-08-11) en base al carrito actual."""
    cart = _get_cart(request)
    seed_ids = [int(pid) for pid in cart.keys()]
    recommended = await ai_gateway_service.recommend_products(session, tenant_id, seed_product_ids=seed_ids)
    return {"recommended": [_serialize_recommendation(p) for p in recommended]}


@router.post("/tienda/carrito/agregar")
def storefront_cart_add(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(1),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    product = session.exec(
        select(Product).where(
            Product.id == product_id, Product.tenant_id == tenant_id, Product.is_deleted == False
        )
    ).first()
    if product and quantity > 0:
        cart = _get_cart(request)
        key = str(product_id)
        cart[key] = cart.get(key, 0) + quantity
        _save_cart(request, cart)
    return RedirectResponse(url="/tienda/carrito", status_code=303)


@router.post("/tienda/carrito/quitar")
def storefront_cart_remove(
    request: Request,
    product_id: int = Form(...),
):
    cart = _get_cart(request)
    cart.pop(str(product_id), None)
    _save_cart(request, cart)
    return RedirectResponse(url="/tienda/carrito", status_code=303)


@router.get("/tienda/carrito", response_class=HTMLResponse)
def storefront_cart_view(
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    settings = _get_store_settings(session, tenant_id)
    cart = _get_cart(request)
    lines = _cart_products(session, tenant_id, cart)
    total = sum(l["line_total"] for l in lines) if lines else 0
    cart_count = sum(cart.values()) if cart else 0

    return _templates().TemplateResponse(
        "storefront_cart.html",
        {"request": request, "settings": settings, "lines": lines, "total": total, "cart_count": cart_count},
    )


@router.post("/tienda/checkout", response_class=HTMLResponse)
def storefront_checkout(
    request: Request,
    buyer_name: str = Form(...),
    buyer_phone: Optional[str] = Form(None),
    buyer_email: Optional[str] = Form(None),
    buyer_address: Optional[str] = Form(None),
    payment_method: str = Form("pendiente"),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    settings = _get_store_settings(session, tenant_id)
    cart = _get_cart(request)
    lines = _cart_products(session, tenant_id, cart)

    if not lines:
        return _templates().TemplateResponse(
            "storefront_cart.html",
            {"request": request, "settings": settings, "lines": [], "total": 0, "cart_count": 0,
             "error": "El carrito está vacío"},
        )

    cart_items = [{"product_id": pid, "quantity": qty} for pid, qty in cart.items()]

    try:
        sale = create_order(
            session=session,
            tenant_id=tenant_id,
            cart_items=cart_items,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            buyer_email=buyer_email,
            buyer_address=buyer_address,
            payment_method=payment_method,
        )
    except StorefrontOrderError as exc:
        total = sum(l["line_total"] for l in lines)
        return _templates().TemplateResponse(
            "storefront_cart.html",
            {"request": request, "settings": settings, "lines": lines, "total": total,
             "cart_count": sum(cart.values()), "error": str(exc)},
        )

    _save_cart(request, {})
    return RedirectResponse(url=f"/tienda/pedido/{sale.id}", status_code=303)


@router.get("/tienda/pedido/{sale_id}", response_class=HTMLResponse)
def storefront_order_confirmation(
    sale_id: int,
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    settings = _get_store_settings(session, tenant_id)
    sale = session.exec(
        select(Sale).where(Sale.id == sale_id, Sale.tenant_id == tenant_id)
    ).first()
    if not sale:
        return _templates().TemplateResponse(
            "storefront_catalog.html",
            {"request": request, "settings": settings, "products": [], "cart_count": 0, "error": "Pedido no encontrado"},
            status_code=404,
        )

    return _templates().TemplateResponse(
        "storefront_order_confirmation.html",
        {"request": request, "settings": settings, "sale": sale, "cart_count": 0},
    )


@router.post("/tienda/alexio/chat")
async def storefront_alexio_chat(
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    payload = await request.json()
    message = (payload.get("message") or "").strip()
    if not message:
        return {"error": "Mensaje vacío"}
    if len(message) > 500:
        return {"error": "Mensaje demasiado largo"}

    history = request.session.get("alexio_history", [])
    # Tope de turnos guardados en sesión, para no acumular indefinidamente.
    history = history[-10:]

    try:
        reply = await ai_brain_service.chat_response(
            session=session,
            tenant_id=tenant_id,
            history=history,
            new_message=message,
            system_instruction=ALEXIO_LIVE_SYSTEM_PROMPT,
            allowed_tools=ALEXIO_LIVE_ALLOWED_TOOLS,
        )
    except ValueError as exc:
        return {"error": str(exc)}

    history.append({"role": "user", "parts": [{"text": message}]})
    history.append({"role": "model", "parts": [{"text": reply}]})
    request.session["alexio_history"] = history[-10:]

    return {"reply": reply}
