from __future__ import annotations

"""
database/models.py — VibeCloud SaaS
=================================
CORRECCIONES APLICADAS:
  1. ui_theme default unificado → "standard" (igual que la migración DB)
  2. Soft delete completo: is_deleted + deleted_at en Supplier, User, Purchase, Location, Bin
  3. Barcode único por tenant (UniqueConstraint tenant_id+barcode), NO global
  4. stock_quantity eliminado de Product → fuente única: SUM(BinStock.quantity)
  5. AccountReceivable nuevo modelo: venta → deuda con balance, due_date, status
  6. PaymentAllocation nuevo modelo: N métodos de pago por venta (reemplaza amount_cash/transfer)
  7. AICredential y BusinessConfig: api_key cifrada con Fernet (ver EncryptedStr)
  8. CashMovement: sale_id + purchase_id restaurados como referencias tipadas
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from cryptography.fernet import Fernet
from sqlalchemy import CheckConstraint, Column, Index, Numeric, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.orm import relationship

import os

# ---------------------------------------------------------------------------
# Cifrado de credenciales (FIX #7)
# Requiere: pip install cryptography
# Configurar variable de entorno: VIBECLOUD_API_KEY=<fernet_key>
# Generar una vez con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    key = os.environ.get("VIBECLOUD_API_KEY")
    if not key:
        raise RuntimeError(
            "VIBECLOUD_API_KEY no está configurada. "
            "Generá una clave con Fernet.generate_key() y agrégala como variable de entorno."
        )
    return Fernet(key.encode())


def encrypt_api_key(plain: str) -> str:
    """Cifra una API key con Fernet. Guardar el resultado en la DB."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_api_key(token: str) -> str:
    """Descifra una API key. Usar solo en memoria, nunca devolver al cliente."""
    return _get_fernet().decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ===========================================================================
# TENANT / MULTI-TENANCY
# ===========================================================================

class Tenant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    subdomain: Optional[str] = Field(default=None, unique=True, index=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)
    
    ai_tier: str = Field(default="free")
    ai_credits: int = Field(default=100)

    # Que productos tiene contratados este tenant -- combinacion libre, no
    # jerarquia (reemplaza al viejo product_plan de un solo nivel).
    # has_erp=False: ERP no se activa por defecto, se habilita explicitamente.
    has_erp: bool = Field(default=False)
    has_ecommerce: bool = Field(default=True)
    has_landing: bool = Field(default=True)
    users: List["User"] = Relationship(sa_relationship=relationship("User", back_populates="tenant"))
    settings: List["Settings"] = Relationship(sa_relationship=relationship("Settings", back_populates="tenant"))


# ===========================================================================
# DOMINIOS CUSTOM (Fase 5 del roadmap -- capa de "hosting provider")
# ===========================================================================

class TenantDomain(SQLModel, table=True):
    """
    Dominio propio conectado por un tenant (además del subdominio gratuito
    vía BASE_DOMAIN). Verificación por TXT record antes de servir tráfico --
    ver services/domain_registrar_service.py.
    """
    __table_args__ = (
        UniqueConstraint("domain", name="uq_tenantdomain_domain"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)

    domain: str = Field(index=True)  # ej. "miempresa.com"
    verification_token: str
    status: str = Field(default="pending")  # pending, verified, failed
    verified_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class SupportTicket(SQLModel, table=True):
    """
    Ticket de soporte de un tenant hacia VibeCloud (centro de ayuda,
    /panel/ayuda). Cualquier usuario del tenant puede crearlo, no solo el
    admin; SuperAdmin los ve todos y responde -- ver routers/superadmin.py.
    """
    __table_args__ = (
        Index("ix_supportticket_tenant_status", "tenant_id", "status"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")

    subject: str
    message: str
    status: str = Field(default="open")  # open, answered, closed
    response: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    responded_at: Optional[datetime] = None


# ===========================================================================
# SETTINGS
# ===========================================================================

class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id")
    tenant: Optional[Tenant] = Relationship(sa_relationship=relationship("Tenant", back_populates="settings"))

    company_name: str = Field(default="VibeCloud")
    logo_url: str = Field(default="/static/images/logo.png")
    tax_rate: Optional[Decimal] = Field(default=Decimal("0.00"), sa_column=Column(Numeric(5, 4), nullable=True))
    printer_name: Optional[str] = Field(default=None)
    label_width_mm: int = Field(default=60)
    label_height_mm: int = Field(default=40)

    # FIX #1: default unificado con la migración DB (server_default='standard')
    ui_theme: str = Field(default="standard")  # standard, minimalist
    storefront_template: str = Field(default="elegante")  # elegante, urbano, natural, tech
    is_onboarded: bool = Field(default=False)
    onboarding_step: int = Field(default=1)

    # Conector ERP<->Ecommerce (Fase 2): apagado = el storefront usa su
    # propio deposito de stock, separado del ERP. Prendido = comparte el
    # mismo stock que el POS/ERP. Lo decide el tenant, no es automatico.
    ecommerce_connected_to_erp: bool = Field(default=False)

    site_config_json: Optional[str] = Field(default=None)


# ===========================================================================
# TAX
# ===========================================================================

class Tax(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    rate: Decimal = Field(default=Decimal("0.21"), sa_column=Column(Numeric(5, 4), nullable=False))
    is_active: bool = Field(default=True)


# ===========================================================================
# CLIENT
# ===========================================================================

class Client(SQLModel, table=True):
    __table_args__ = (
        Index("ix_client_tenant_name", "tenant_id", "name"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)

    name: str = Field(index=True)
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    credit_limit: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    credit_enabled: bool = Field(default=False)

    razon_social: Optional[str] = None
    cuit: Optional[str] = None
    iva_category: Optional[str] = None
    transport_name: Optional[str] = None
    transport_address: Optional[str] = None

    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)

    sales: List["Sale"] = Relationship(sa_relationship=relationship("Sale", back_populates="client"))
    payments: List["Payment"] = Relationship(sa_relationship=relationship("Payment", back_populates="client"))
    receivables: List["AccountReceivable"] = Relationship(sa_relationship=relationship("AccountReceivable", back_populates="client"))


# ===========================================================================
# USER
# ===========================================================================

class User(SQLModel, table=True):
    # Username unico POR TENANT, no a nivel de toda la plataforma -- con
    # muchos tenants distintos (modelo de negocio: vender a muchos clientes),
    # dos negocios distintos tienen que poder tener cada uno su propio
    # usuario "admin" sin chocar entre si.
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_user_tenant_username"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    tenant: Optional[Tenant] = Relationship(sa_relationship=relationship("Tenant", back_populates="users"))

    username: str = Field(index=True)
    password_hash: str
    full_name: Optional[str] = None
    email: Optional[str] = Field(default=None)
    role: str = Field(default="admin")  # admin, cashier, seller, client
    client_id: Optional[int] = Field(default=None, foreign_key="client.id")
    # False mientras espera confirmar el mail (solo cuando ese modo esta
    # activo, ver services/email_service.py) -- reusa el flag que login()
    # ya chequea, no hace falta un campo nuevo para esto.
    is_active: bool = Field(default=False if False else True)

    # FIX #2: soft delete en User
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)

    sales: List["Sale"] = Relationship(sa_relationship=relationship("Sale", back_populates="user"))


# ===========================================================================
# PRODUCT
# ===========================================================================

class TenantCatalog(SQLModel, table=True):
    """
    Tabla puente para almacenar qué productos mayoristas habilita cada minorista (Tenant)
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)

    # Relationship placeholders if needed later
    # tenant: Optional["Tenant"] = Relationship()
    # product: Optional["Product"] = Relationship()


class LandingPage(SQLModel, table=True):
    """
    Landing page generada por IA (Fase 3 del roadmap, "AI Template Studio").
    El contenido se guarda como JSON ya validado contra LandingPageContent
    (services/landing_service.py) -- nunca HTML/CSS crudo generado por el
    modelo, Regla 1.2 de CLAUDE.md.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True, unique=True)

    prompt_used: str
    content_json: str  # LandingPageContent serializado, ya validado
    # Imagen de referencia de estilo subida por el tenant en el wizard de
    # onboarding (Fase 4) -- solo se guarda la ruta del archivo, nunca se
    # persiste como texto/base64 en la DB. Se le manda a Gemini como
    # referencia estetica (colores/ambiente), nunca se copia literal --
    # ver services/landing_service.py SYSTEM_INSTRUCTION.
    reference_image_url: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

class Product(SQLModel, table=True):
    """
    FIX #3: barcode único POR TENANT, no global.
    FIX #4: stock_quantity eliminado → usar SUM(BinStock.quantity) via StockService.
    """

    __table_args__ = (
        # Barcode único por tenant: dos tenants pueden tener el mismo código
        UniqueConstraint("tenant_id", "barcode", name="uq_product_tenant_barcode"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)

    name: str
    description: Optional[str] = None
    barcode: str = Field(index=True)  # unique por tenant, no global

    price: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))
    price_bulk: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    price_retail: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))

    medusa_product_id: Optional[str] = Field(default=None, index=True)
    cost_price: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))

    # ELIMINADO: stock_quantity — fuente única de verdad es BinStock
    # Para leer stock: SELECT SUM(bs.quantity) FROM binstock bs WHERE bs.product_id = ? AND bs.tenant_id = ?
    # StockService.get_total_stock(session, product_id, tenant_id) ya implementa esto.

    min_stock_level: int = Field(default=5)
    category: Optional[str] = None
    item_number: Optional[str] = Field(default=None, index=True)
    image_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    cant_bulto: Optional[int] = Field(default=None)
    numeracion: Optional[str] = None
    curve_quantity: int = Field(default=1)

    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)

    @property
    def stock_quantity(self) -> int:
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session is not None and self.id is not None:
            from database.models import BinStock
            from sqlmodel import select
            from sqlalchemy import func
            total = session.exec(select(func.sum(BinStock.quantity)).where(BinStock.product_id == self.id, BinStock.tenant_id == self.tenant_id)).one()
            return total or 0
        return 0

    @stock_quantity.setter
    def stock_quantity(self, value: int):
        pass

from sqlalchemy import Text, Index, inspect, Column, JSON
from sqlalchemy.dialects.postgresql import JSONB
import uuid as uuid_module
from typing import Any, Dict

class SyncQueue(SQLModel, table=True):
    __tablename__ = "sync_queue"

    __table_args__ = (
        Index("ix_sync_queue_tenant_status", "tenant_id", "status"),
    )

    id: str = Field(
        default_factory=lambda: str(uuid_module.uuid4()),
        primary_key=True
    )
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    entity_type: str = Field(index=True)  # 'product' | 'inventory' | 'price'
    entity_id: str = Field(index=True)
    payload: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSONB().with_variant(JSON(), "sqlite"))
    )
    status: str = Field(default="pending", index=True)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=5)
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProcessedWebhook(SQLModel, table=True):
    __tablename__ = "processed_webhooks"

    event_id: str = Field(primary_key=True)
    source: str = Field(default="medusa")
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="processed")

# ===========================================================================
# SALE / SALE ITEM
# ===========================================================================

class Sale(SQLModel, table=True):
    """
    FIX #6: amount_cash y amount_transfer eliminados del header.
    Los métodos de pago viven en PaymentAllocation (1 venta → N pagos).
    """

    __table_args__ = (
        Index("ix_sale_tenant_timestamp", "tenant_id", "timestamp"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)

    timestamp: datetime = Field(default_factory=_utcnow)
    total_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))
    amount_paid: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))
    payment_status: str = Field(default="paid")  # paid, partial, pending
    is_closed: bool = Field(default=False)

    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional[User] = Relationship(sa_relationship=relationship("User", back_populates="sales"))

    client_id: Optional[int] = Field(default=None, foreign_key="client.id")
    client: Optional["Client"] = Relationship(sa_relationship=relationship("Client", back_populates="sales"))

    items: List["SaleItem"] = Relationship(sa_relationship=relationship("SaleItem", back_populates="sale"))
    payment_allocations: List["PaymentAllocation"] = Relationship(sa_relationship=relationship("PaymentAllocation", back_populates="sale"))
    receivable: Optional["AccountReceivable"] = Relationship(sa_relationship=relationship("AccountReceivable", back_populates="sale"))

    @property
    def payment_method(self) -> str:
        if not self.payment_allocations:
            return "cuenta_corriente"
        if len(self.payment_allocations) == 1:
            return self.payment_allocations[0].method
        methods = {pa.method for pa in self.payment_allocations}
        if len(methods) == 1:
            return list(methods)[0]
        return "combinado"

    @payment_method.setter
    def payment_method(self, value: str):
        pass


class SaleItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sale_id: Optional[int] = Field(default=None, foreign_key="sale.id")
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    product: Optional["Product"] = Relationship(sa_relationship=relationship("Product", lazy="joined"))

    product_name: str  # snapshot
    quantity: int
    unit_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    total: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    cost_price_at_sale: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))

    sale: Optional[Sale] = Relationship(sa_relationship=relationship("Sale", back_populates="items"))


# ===========================================================================
# PAYMENT ALLOCATION (FIX #6: reemplaza amount_cash / amount_transfer en Sale)
# ===========================================================================

class PaymentAllocation(SQLModel, table=True):
    """
    Permite múltiples métodos de pago por venta.
    Ejemplo: Sale(total=10000) → [efectivo: 7000, transferencia: 3000]
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    sale_id: int = Field(foreign_key="sale.id", index=True)
    method: str  # "cash", "transfer", "qr", "credit", "debit"
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    sale: Optional[Sale] = Relationship(sa_relationship=relationship("Sale", back_populates="payment_allocations"))


# ===========================================================================
# ACCOUNT RECEIVABLE (FIX #5: cuentas corrientes reales)
# ===========================================================================

class AccountReceivable(SQLModel, table=True):
    """
    Representa la deuda generada por una venta a cuenta corriente.
    Permite generar Excel de cuenta corriente por factura por cliente.

    Flujo:
      Sale (payment_status='pending') → crea AccountReceivable
      Payment → reduce AccountReceivable.balance → actualiza status
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id")

    sale_id: int = Field(foreign_key="sale.id", unique=True, index=True)
    client_id: int = Field(foreign_key="client.id", index=True)

    invoice_number: Optional[str] = Field(default=None, index=True)
    total: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    paid: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))
    balance: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))  # = total - paid (actualizar al registrar Payment)

    issued_at: datetime = Field(default_factory=_utcnow)
    due_date: Optional[datetime] = Field(default=None)
    status: str = Field(default="pending")  # pending, partial, paid, overdue

    sale: Optional[Sale] = Relationship(sa_relationship=relationship("Sale", back_populates="receivable"))
    client: Optional[Client] = Relationship(sa_relationship=relationship("Client", back_populates="receivables"))
    payments: List["Payment"] = Relationship(sa_relationship=relationship("Payment", back_populates="receivable"))


# ===========================================================================
# PAYMENT (pagos sobre cuenta corriente)
# ===========================================================================

class Payment(SQLModel, table=True):
    """
    Pago que cancela (total o parcialmente) un AccountReceivable.
    Relaciona: cliente → deuda → pago.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id")
    client_id: int = Field(foreign_key="client.id")

    # Relación a la deuda específica que cancela
    receivable_id: Optional[int] = Field(default=None, foreign_key="accountreceivable.id", index=True)

    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    method: str = Field(default="cash")  # cash, transfer, qr, etc.
    date: datetime = Field(default_factory=_utcnow)
    note: Optional[str] = None

    client: Optional[Client] = Relationship(sa_relationship=relationship("Client", back_populates="payments"))
    receivable: Optional[AccountReceivable] = Relationship(sa_relationship=relationship("AccountReceivable", back_populates="payments"))


# ===========================================================================
# SUPPLIER
# ===========================================================================

class Supplier(SQLModel, table=True):
    __table_args__ = (
        Index("ix_supplier_tenant_name", "tenant_id", "name"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)

    name: str = Field(index=True)
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    cuit: Optional[str] = None
    notes: Optional[str] = None

    # FIX #2: soft delete en Supplier
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)

    purchases: List["Purchase"] = Relationship(sa_relationship=relationship("Purchase", back_populates="supplier"))


# ===========================================================================
# PURCHASE / PURCHASE ITEM
# ===========================================================================

class Purchase(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id")
    supplier_id: Optional[int] = Field(default=None, foreign_key="supplier.id")

    timestamp: datetime = Field(default_factory=_utcnow)
    invoice_number: Optional[str] = None
    total_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(12, 2), nullable=False))
    status: str = Field(default="pending")  # pending, paid

    # FIX #2: soft delete en Purchase
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)

    supplier: Optional[Supplier] = Relationship(sa_relationship=relationship("Supplier", back_populates="purchases"))
    items: List["PurchaseItem"] = Relationship(sa_relationship=relationship("PurchaseItem", back_populates="purchase"))


class PurchaseItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    purchase_id: int = Field(foreign_key="purchase.id")
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")

    product_name: str
    quantity: int
    unit_cost: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    total: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))

    purchase: Optional[Purchase] = Relationship(sa_relationship=relationship("Purchase", back_populates="items"))


# ===========================================================================
# CASH MOVEMENT (FIX #8: sale_id y purchase_id restaurados)
# ===========================================================================

class CashMovement(SQLModel, table=True):
    """
    FIX #8: sale_id y purchase_id son columnas tipadas con FK real,
    además de reference_id/reference_type para movimientos manuales.
    Esto restaura la trazabilidad histórica que se perdió con el drop_column.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id")

    timestamp: datetime = Field(default_factory=_utcnow)
    movement_type: str = Field(index=True)  # "in", "out", "cierre"
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    concept: str

    # Trazabilidad directa (restaurada)
    sale_id: Optional[int] = Field(default=None, foreign_key="sale.id", index=True)
    purchase_id: Optional[int] = Field(default=None, foreign_key="purchase.id", index=True)

    # Trazabilidad genérica para movimientos manuales
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None  # "manual", "expense", etc.

    user_id: Optional[int] = Field(default=None, foreign_key="user.id")


# ===========================================================================
# WMS: LOCATION / BIN / BIN STOCK / STOCK MOVEMENT
# ===========================================================================

class Location(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_location_tenant_code"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)

    name: str = Field(index=True)
    code: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)

    # FIX #2: soft delete en Location
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)

    bins: List["Bin"] = Relationship(sa_relationship=relationship("Bin", back_populates="location"))


class Bin(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tenant_id", "location_id", "name", name="uq_bin_tenant_location_name"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    location_id: int = Field(foreign_key="location.id", index=True)

    name: str
    aisle: Optional[str] = None
    shelf: Optional[str] = None
    position: Optional[str] = None
    max_capacity: Optional[int] = None
    description: Optional[str] = None
    is_active: bool = Field(default=True)

    # FIX #2: soft delete en Bin
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)

    location: Optional[Location] = Relationship(sa_relationship=relationship("Location", back_populates="bins"))
    stock_entries: List["BinStock"] = Relationship(sa_relationship=relationship("BinStock", back_populates="bin"))


class BinStock(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("bin_id", "product_id", name="uq_binstock_bin_product"),
        CheckConstraint("quantity >= 0", name="ck_bin_stock_qty_non_negative"),
        Index("ix_bin_stock_tenant_product", "tenant_id", "product_id"),
        Index("ix_bin_stock_tenant_bin", "tenant_id", "bin_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id")
    bin_id: int = Field(foreign_key="bin.id")
    product_id: int = Field(foreign_key="product.id")

    quantity: int = Field(default=0)  # >= 0 enforced por CHECK
    updated_at: datetime = Field(default_factory=_utcnow)

    bin: Optional[Bin] = Relationship(sa_relationship=relationship("Bin", back_populates="stock_entries"))


class StockMovement(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_movement_qty_positive"),
        CheckConstraint(
            "from_bin_id IS NOT NULL OR to_bin_id IS NOT NULL",
            name="ck_movement_any_side",
        ),
        Index("ix_movement_tenant_time", "tenant_id", "timestamp"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)

    product_id: int = Field(foreign_key="product.id")
    from_bin_id: Optional[int] = Field(default=None, foreign_key="bin.id")
    to_bin_id: Optional[int] = Field(default=None, foreign_key="bin.id")

    quantity: int
    reason: Optional[str] = None   # "ingreso", "transferencia", "ajuste", "venta"
    notes: Optional[str] = None
    request_id: Optional[str] = None  # idempotencia

    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    timestamp: datetime = Field(default_factory=_utcnow)


# ===========================================================================
# AI / CREDENTIALS (FIX #7: api_key cifrada con Fernet)
# ===========================================================================

class BusinessConfig(SQLModel, table=True):
    """
    FIX #7: Las API keys se guardan CIFRADAS con Fernet.
    Usar encrypt_api_key() al guardar, decrypt_api_key() al usar en memoria.
    NUNCA devolver el valor descifrado al cliente HTTP.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_name: str
    tier: str = Field(default="standard")

    # Almacenar siempre el resultado de encrypt_api_key(plain_key)
    openai_api_key_enc: Optional[str] = None
    deepseek_api_key_enc: Optional[str] = None
    elevenlabs_api_key_enc: Optional[str] = None

    system_prompt: Optional[str] = "Eres un asistente de ventas útil."
    voice_id: Optional[str] = None
    is_active: bool = Field(default=True)


class AICredential(SQLModel, table=True):
    """
    FIX #7: api_key_enc reemplaza api_key (texto plano eliminado).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", unique=True, index=True)
    provider: str = Field(default="gemini")

    # NUNCA guardar la clave original. Guardar encrypt_api_key(plain).
    api_key_enc: str


# ===========================================================================
# REFRESH TOKEN (FASE 1: JWT)
# ===========================================================================

class RefreshToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=_utcnow)
    revoked_at: Optional[datetime] = None


# ===========================================================================
# UI CONFIG (FASE 2: GESTOR DE UI)
# ===========================================================================

class PlatformPayment(SQLModel, table=True):
    __table_args__ = (
        Index("ix_platformpayment_tenant", "tenant_id"),
        Index("ix_platformpayment_external", "provider", "external_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    provider: str = Field(index=True)
    external_id: str = Field(default="")
    payment_type: str
    amount: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(12, 2)))
    currency: str = Field(default="USD")
    status: str = Field(default="pending")
    description: str = Field(default="")
    metadata_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    sale_id: Optional[int] = Field(default=None, foreign_key="sale.id")


class UIConfig(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tenant_id", "page_name", name="uq_uiconfig_tenant_page"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    page_name: str = Field(index=True)  # "pos", "dashboard", "storefront_home"
    layout_json: str
    theme_json: str
    updated_at: datetime = Field(default_factory=_utcnow)


# ===========================================================================
# VIBECLOUD — VALIDATION PIPELINE
# ===========================================================================

class ResearchProject(SQLModel, table=True):
    __table_args__ = (
        Index("ix_researchproject_tenant_status", "tenant_id", "status"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")

    project_type: str = Field(default="physical_product")  # physical_product, digital_service
    query_description: str
    reference_url: Optional[str] = None
    factory_price: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    status: str = Field(default="draft")  # draft, researching, completed, error

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    listings: List["ResearchListing"] = Relationship(sa_relationship=relationship("ResearchListing", back_populates="project"))
    demand: Optional["ResearchDemand"] = Relationship(sa_relationship=relationship("ResearchDemand", back_populates="project", uselist=False))
    competitors: List["CompetitorAnalysis"] = Relationship(sa_relationship=relationship("CompetitorAnalysis", back_populates="project"))
    offers: List["Offer"] = Relationship(sa_relationship=relationship("Offer", back_populates="project"))
    forecasts: List["ResearchForecast"] = Relationship(sa_relationship=relationship("ResearchForecast", back_populates="project"))


class ResearchListing(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="researchproject.id", index=True)

    source: str  # Amazon, MercadoLibre, Keepa, demo
    title: str
    price: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    currency: str = Field(default="USD")
    url: Optional[str] = None
    rating: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(3, 2), nullable=True))
    review_count: Optional[int] = None
    is_demo: bool = Field(default=False)

    created_at: datetime = Field(default_factory=_utcnow)

    project: Optional[ResearchProject] = Relationship(sa_relationship=relationship("ResearchProject", back_populates="listings"))


class ResearchDemand(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_researchdemand_project"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="researchproject.id", index=True)

    confidence_level: str = Field(default="no_disponible")  # alto, medio, bajo, no_disponible
    estimated_monthly_volume: Optional[int] = None
    source_description: Optional[str] = None
    notes: Optional[str] = None

    project: Optional[ResearchProject] = Relationship(sa_relationship=relationship("ResearchProject", back_populates="demand"))


class CompetitorAnalysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="researchproject.id", index=True)

    url: str
    value_proposition: Optional[str] = None
    price_info: Optional[str] = None
    guarantees: Optional[str] = None
    objections_addressed: Optional[str] = None
    analysis_json: Optional[str] = None
    user_confirmed: bool = Field(default=False)

    created_at: datetime = Field(default_factory=_utcnow)

    project: Optional[ResearchProject] = Relationship(sa_relationship=relationship("ResearchProject", back_populates="competitors"))


class Offer(SQLModel, table=True):
    __table_args__ = (
        Index("ix_offer_tenant_project", "tenant_id", "project_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    project_id: int = Field(foreign_key="researchproject.id", index=True)

    title: str
    value_proposition: str
    price_structure: str
    cta_text: str = Field(default="Comprar ahora")
    differentiators_json: Optional[str] = None
    status: str = Field(default="draft")  # draft, pending_validation, validated, rejected
    version: int = Field(default=1)

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    project: Optional[ResearchProject] = Relationship(sa_relationship=relationship("ResearchProject", back_populates="offers"))
    debate: Optional["ValidationDebate"] = Relationship(sa_relationship=relationship("ValidationDebate", back_populates="offer", uselist=False))


class ValidationDebate(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("offer_id", name="uq_validationdebate_offer"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key="offer.id", index=True)

    status: str = Field(default="in_progress")  # in_progress, completed
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None
    final_verdict: Optional[str] = None  # approved, needs_revision
    arbiter_summary: Optional[str] = None

    offer: Optional[Offer] = Relationship(sa_relationship=relationship("Offer", back_populates="debate"))
    objections: List["DebateObjection"] = Relationship(sa_relationship=relationship("DebateObjection", back_populates="debate"))


class DebateObjection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="validationdebate.id", index=True)

    objection_text: str
    objection_source: str  # devil_advocate, price_skeptic, market_analyst, customer_sim
    severity: str = Field(default="medium")  # high, medium, low
    proposed_solution: Optional[str] = None
    resolution_status: str = Field(default="pending")  # pending, resolved, dismissed
    resolved_text: Optional[str] = None
    order_index: int = Field(default=0)

    debate: Optional[ValidationDebate] = Relationship(sa_relationship=relationship("ValidationDebate", back_populates="objections"))


# ===========================================================================
# DEBATE DE PERSONAS — Expertos humanos validan ofertas
# ===========================================================================

class ExpertDebate(SQLModel, table=True):
    __table_args__ = (
        Index("ix_expertdebate_offer_tenant", "offer_id", "tenant_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key="offer.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)

    status: str = Field(default="open")  # open, closed
    created_at: datetime = Field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None
    summary: Optional[str] = None

    opinions: List["ExpertOpinion"] = Relationship(
        sa_relationship=relationship("ExpertOpinion", back_populates="debate", order_by="ExpertOpinion.created_at")
    )


class ExpertOpinion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="expertdebate.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)

    expert_name: str
    expert_role: str  # marketing, finance, operations, industry, ux
    expert_email: Optional[str] = None

    opinion_text: str
    verdict: str = Field(default="neutral")  # approve, reject, neutral
    suggestions: Optional[str] = None
    source: str = Field(default="ai_generated")  # ai_generated, manual

    created_at: datetime = Field(default_factory=_utcnow)

    debate: Optional[ExpertDebate] = Relationship(
        sa_relationship=relationship("ExpertDebate", back_populates="opinions")
    )


# ===========================================================================
# TIMESFM — PREDICCION DE MERCADO (Google TimesFM 2.5, Apache-2.0)
# ===========================================================================

class ResearchForecast(SQLModel, table=True):
    """
    Prediccion de tendencia de precios y demanda generada por TimesFM
    (Google Research Time Series Foundation Model) para un ResearchProject.
    Los campos price_series, forecast_series, confidence_low, confidence_high
    almacenan arrays JSON de floats para graficar en el frontend.
    """
    __table_args__ = (
        UniqueConstraint("project_id", "horizon_days", name="uq_researchforecast_project_horizon"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="researchproject.id", index=True)

    horizon_days: int = Field(default=30)  # 30 o 90

    # Series como JSON arrays: "[29.99, 31.5, 33.0, ...]"
    price_series: Optional[str] = None        # historico de precios observados
    forecast_series: Optional[str] = None     # prediccion de precios
    confidence_low: Optional[str] = None      # banda inferior de confianza
    confidence_high: Optional[str] = None     # banda superior de confianza

    # Analisis textual generado por Gemini a partir del forecast
    trend_direction: str = Field(default="estable")  # alcista, bajista, estable
    launch_window: Optional[str] = None       # "Q4 2026", "Enero-Febrero 2027"
    recommendation: Optional[str] = None      # texto de recomendacion de lanzamiento
    provider: str = Field(default="timesfm_simulated")  # timesfm_api, timesfm_simulated

    created_at: datetime = Field(default_factory=_utcnow)

    project: Optional["ResearchProject"] = Relationship(
        sa_relationship=relationship("ResearchProject", back_populates="forecasts")
    )


class ForecastProfile(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_forecastprofile_project"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    project_id: int = Field(foreign_key="researchproject.id", index=True)

    business_type: str = Field(default="physical_product")
    business_stage: str = Field(default="idea")
    product_category: Optional[str] = None
    target_market: str = Field(default="national")
    target_audience: Optional[str] = None
    unit_cost: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    desired_margin_pct: Optional[int] = None
    known_competitor_prices: Optional[str] = None
    pricing_strategy: str = Field(default="competitive")
    geography: Optional[str] = None
    seasonality_notes: Optional[str] = None
    competition_level: str = Field(default="medium")
    differentiator: Optional[str] = None
    launch_target_date: Optional[str] = None
    monthly_revenue_target: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    growth_expectation: str = Field(default="moderate")

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None

    project: Optional["ResearchProject"] = Relationship(
        sa_relationship=relationship("ResearchProject", backref="forecast_profile")
    )
