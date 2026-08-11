"""Checkout público del ecommerce propio (Fase 2 del roadmap).

No hay pasarela de pago integrada todavía (no definida) -- el pedido se crea
con payment_status="pending" y el vendedor confirma el pago manualmente
(efectivo/transferencia) desde el panel, igual que ya hace con ventas del POS.

Reutiliza StockService.process_sale para el locking de stock (misma lógica
que el POS), pero SIN pasarle client_id -- eso evita el chequeo de límite de
crédito de process_sale (pensado para clientes con cuenta corriente, no
aplica a un comprador anónimo online). El Client se crea/asocia después,
sobre la Sale ya creada, solo para que el vendedor tenga los datos de
contacto y entrega.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from database.models import Client, Product, Sale, Settings, TenantCatalog
from services.stock_service import StockService

stock_service = StockService()


class StorefrontOrderError(ValueError):
    pass


def _get_or_create_buyer_client(
    session: Session,
    tenant_id: int,
    name: str,
    phone: Optional[str],
    email: Optional[str],
    address: Optional[str],
) -> Client:
    existing = None
    if email:
        existing = session.exec(
            select(Client).where(Client.tenant_id == tenant_id, Client.email == email, Client.is_deleted == False)
        ).first()
    if not existing and phone:
        existing = session.exec(
            select(Client).where(Client.tenant_id == tenant_id, Client.phone == phone, Client.is_deleted == False)
        ).first()

    if existing:
        # Actualiza datos de contacto/entrega con lo mas reciente del checkout.
        existing.name = name or existing.name
        existing.phone = phone or existing.phone
        existing.email = email or existing.email
        existing.address = address or existing.address
        session.add(existing)
        return existing

    client = Client(tenant_id=tenant_id, name=name, phone=phone, email=email, address=address)
    session.add(client)
    session.flush()
    return client


def create_order(
    session: Session,
    tenant_id: int,
    cart_items: list[dict],
    buyer_name: str,
    buyer_phone: Optional[str] = None,
    buyer_email: Optional[str] = None,
    buyer_address: Optional[str] = None,
    payment_method: str = "pendiente",
) -> Sale:
    """
    cart_items: [{"product_id": int, "quantity": int}, ...]
    Valida que cada producto pertenezca al tenant resuelto por dominio
    (nunca confía en tenant_id del carrito) y, si el tenant curó su catálogo
    (TenantCatalog), que el producto esté habilitado para venta pública.
    """
    if not cart_items:
        raise StorefrontOrderError("El carrito está vacío")
    if not buyer_name or not buyer_name.strip():
        raise StorefrontOrderError("Falta el nombre del comprador")

    curated_ids = set(
        session.exec(select(TenantCatalog.product_id).where(TenantCatalog.tenant_id == tenant_id)).all()
    )

    items_data = []
    for item in cart_items:
        product_id = int(item["product_id"])
        quantity = int(item["quantity"])
        if quantity <= 0:
            continue

        product = session.exec(
            select(Product).where(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
                Product.is_deleted == False,
            )
        ).first()
        if not product:
            raise StorefrontOrderError(f"Producto {product_id} no disponible en esta tienda")
        if curated_ids and product.id not in curated_ids:
            raise StorefrontOrderError(f"Producto {product.name} no está habilitado para venta pública")

        items_data.append({"product_id": product_id, "quantity": quantity})

    if not items_data:
        raise StorefrontOrderError("El carrito está vacío")

    # Conector ERP<->Ecommerce (Fase 2): si el tenant lo dejó apagado, el
    # storefront descuenta de su propio deposito "ONLINE", separado del que
    # usa el POS/ERP. Si está prendido, comparte el mismo stock (comportamiento
    # de siempre, target_bin_name=None -> SIN-UBICACION / bin activo).
    settings = session.exec(select(Settings).where(Settings.tenant_id == tenant_id)).first()
    connected = bool(settings and settings.ecommerce_connected_to_erp)
    target_bin_name = None if connected else "ONLINE"

    # user_id=None, client_id=None: process_sale no dispara el chequeo de
    # crédito (solo corre si client_id está seteado) y Sale.user_id/
    # StockMovement.user_id son nullable -- una venta online no tiene un
    # usuario del staff detrás.
    try:
        sale = stock_service.process_sale(
            session=session,
            user_id=None,
            tenant_id=tenant_id,
            items_data=items_data,
            payment_method=payment_method,
            client_id=None,
            amount_paid=0,
            target_bin_name=target_bin_name,
        )
    except ValueError as exc:
        # Sin stock suficiente (frecuente ahora que, desconectado del ERP, la
        # tienda tiene su propio deposito "ONLINE" que puede estar vacio) ->
        # mensaje entendible para el comprador, no un 500.
        raise StorefrontOrderError(str(exc)) from exc

    buyer = _get_or_create_buyer_client(
        session, tenant_id, buyer_name.strip(), buyer_phone, buyer_email, buyer_address
    )
    sale.client_id = buyer.id
    session.add(sale)
    session.commit()
    session.refresh(sale)
    return sale
