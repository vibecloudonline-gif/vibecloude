"""VibeCloud Cloud SaaS — Main Application (Refactored)"""
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, func
from sqlalchemy import text
from contextlib import asynccontextmanager
from datetime import datetime, date
import os
import logging
import httpx
from pythonjsonlogger import jsonlogger
from core.config import settings
from database.session import create_db_and_tables, get_session, engine
from database.models import Product, Sale, Settings, User, Tenant
from database.seed_data import seed_products
from services.auth_service import AuthService
from web.dependencies import get_current_user, get_settings, get_tenant, require_auth
from web.compat_templates import CompatTemplates

# Routers
from routers.auth import router as auth_router
from routers.admin import router as admin_router
from routers.products import router as products_router
from routers.sales import router as sales_router
from routers.clients import router as clients_router
from routers.suppliers import router as suppliers_router
from routers.cash import router as cash_router
from routers.reports import router as reports_router
from routers.picking import router as picking_router
from routers.wms import router as wms_router

# API V1 Routers
from routers.api.v1.auth import router as auth_v1_router
from routers.api.v1.products import router as products_v1_router
from routers.api.v1.sales import router as sales_v1_router
from routers.api.v1.ui_config import router as ui_config_v1_router
from routers.api.v1.inventory import router as inventory_v1_router
from routers.ai import router as ai_router
from routers.superadmin import router as superadmin_router
from routers.store import router as store_router
from routers.catalog_import import router as catalog_import_router
from routers.storefront import router as storefront_router
from routers.landing_studio import router as landing_studio_router

from core.logging_config import setup_logging
from core.startup import lifespan

setup_logging()
logger = logging.getLogger(__name__)

templates = CompatTemplates(directory="templates")



from core.limiter import limiter, HAS_SLOWAPI
if HAS_SLOWAPI:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

app = FastAPI(title="VibeCloud Cloud", lifespan=lifespan)
if HAS_SLOWAPI:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# CORS
def _get_cors_origins() -> list[str]:
    env = os.getenv("ENVIRONMENT", "development").lower()
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw:
        if env == "production":
            raw = "https://vibecloud-frontend.onrender.com,https://vibecloud.onrender.com"
        else:
            raw = "http://localhost,http://127.0.0.1,https://vibecloud-frontend.onrender.com"
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if env == "production":
        unsafe = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
        if unsafe:
            logger.warning(f"ADVERTENCIA DE SEGURIDAD: Orígenes no seguros detectados en CORS_ORIGINS en producción: {unsafe}")
    return origins

app.add_middleware(CORSMiddleware, allow_origins=_get_cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


from starlette.middleware.sessions import SessionMiddleware
SESSION_SECRET = os.getenv("SECRET_KEY")
if not SESSION_SECRET:
    raise ValueError("SECRET_KEY es obligatoria en producción para SessionMiddleware.")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.getenv("ENVIRONMENT", "development").lower() == "production",
)


app.mount("/static", StaticFiles(directory="static"), name="static")

# Register all routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(products_router)
app.include_router(sales_router)
app.include_router(clients_router)
app.include_router(suppliers_router)
app.include_router(cash_router)
app.include_router(reports_router)
app.include_router(picking_router)
app.include_router(wms_router)
app.include_router(catalog_import_router)
app.include_router(storefront_router)
app.include_router(landing_studio_router)

# Register API V1 Routers
app.include_router(auth_v1_router, prefix="/api/v1", tags=["Auth V1"])
app.include_router(products_v1_router, prefix="/api/v1", tags=["Products V1"])
app.include_router(sales_v1_router, prefix="/api/v1", tags=["Sales V1"])
app.include_router(ui_config_v1_router, prefix="/api/v1/ui-config", tags=["UI Config V1"])
app.include_router(ui_config_v1_router, prefix="/api/v1", tags=["UI Config V1 (Legacy)"], deprecated=True)
app.include_router(inventory_v1_router, prefix="/api/v1/inventory", tags=["Inventory V1"])



app.include_router(ai_router)
app.include_router(store_router)
app.include_router(superadmin_router)


@app.get("/health")
@app.head("/health")
async def health_check(session: Session = Depends(get_session)):
    status = "healthy"
    services = {"database": "ok"}
    try:
        session.execute(text("SELECT 1"))
    except Exception as e:
        status = "degraded"
        services["database"] = f"error: {str(e)}"
        
    return {"status": status, "services": services}


@app.get("/ready")
async def readiness_check(session: Session = Depends(get_session)):
    """Distinto de /health: si la DB no responde, devuelve 503 -- para que el
    orquestador (Render/DO) saque la instancia del balanceador en vez de
    reportarla como sana con un servicio caído."""
    try:
        session.execute(text("SELECT 1"))
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": str(e)})
    return {"status": "ready"}


@app.get("/", response_class=HTMLResponse)
@app.head("/")
def get_dashboard(request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session)):
    if user.role == "superadmin":
        return RedirectResponse("/tenants", status_code=302)
    total_products = session.exec(select(func.count(Product.id)).where(Product.tenant_id == tenant_id)).one()
    from database.models import BinStock
    from sqlalchemy.sql.functions import coalesce

    subquery = (
        select(Product.id)
        .join(BinStock, BinStock.product_id == Product.id, isouter=True)
        .where(Product.tenant_id == tenant_id, Product.is_deleted == False)
        .group_by(Product.id, Product.min_stock_level)
        .having(coalesce(func.sum(BinStock.quantity), 0) < Product.min_stock_level)
        .subquery()
    )
    low_stock = session.exec(select(func.count()).select_from(subquery)).one()
            
    recent_sales = session.exec(select(Sale).where(Sale.tenant_id == tenant_id, Sale.is_closed == False).order_by(Sale.timestamp.desc()).limit(5)).all()
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_sales_total = session.exec(select(func.sum(Sale.total_amount)).where(Sale.tenant_id == tenant_id, Sale.timestamp >= today_start, Sale.is_closed == False)).one() or 0.0
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "home", "settings": settings, "user": user, "total_products": total_products, "low_stock": low_stock, "recent_sales": recent_sales, "today_sales_total": today_sales_total})


@app.get("/pos", response_class=HTMLResponse)
def get_pos(request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse("pos.html", {"request": request, "active_page": "pos", "settings": settings, "user": user})

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    with open('crash.log', 'w') as f:
        f.write(traceback.format_exc())
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(str(exc), status_code=500)
