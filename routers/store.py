from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List
from database.session import get_session
from database.models import Settings, User, TenantCatalog, Product
from web.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/api/v1/store", tags=["Store Settings"])

class ThemeUpdateRequest(BaseModel):
    theme_id: str

@router.put("/theme")
async def update_store_theme(req: ThemeUpdateRequest, db: Session = Depends(get_session), current_user: User = Depends(require_roles(["admin", "superadmin"]))):
    settings = db.exec(select(Settings).where(Settings.tenant_id == current_user.tenant_id)).first()
    if not settings:
        settings = Settings(tenant_id=current_user.tenant_id, company_name="VibeCloud", ui_theme=req.theme_id)
        db.add(settings)
    else:
        settings.ui_theme = req.theme_id
    db.commit()
    return {"success": True, "theme_id": req.theme_id}

class OnboardingProgressRequest(BaseModel):
    step: int
    company_name: str = None
    description: str = None

@router.put("/onboarding-progress")
async def update_onboarding_progress(req: OnboardingProgressRequest, db: Session = Depends(get_session), current_user: User = Depends(require_roles(["admin", "superadmin"]))):
    settings = db.exec(select(Settings).where(Settings.tenant_id == current_user.tenant_id)).first()
    if not settings:
        settings = Settings(tenant_id=current_user.tenant_id, company_name=req.company_name or "VibeCloud", onboarding_step=req.step)
        db.add(settings)
    else:
        settings.onboarding_step = req.step
        if req.company_name:
            settings.company_name = req.company_name
    db.commit()
    return {"success": True, "step": req.step}

class CatalogSelectionRequest(BaseModel):
    product_ids: List[int]

@router.post("/catalog")
async def save_tenant_catalog(req: CatalogSelectionRequest, db: Session = Depends(get_session), current_user: User = Depends(require_roles(["admin", "superadmin"]))):
    # Full override logic
    existing = db.exec(select(TenantCatalog).where(TenantCatalog.tenant_id == current_user.tenant_id)).all()
    for item in existing:
        db.delete(item)
    
    for pid in req.product_ids:
        db.add(TenantCatalog(tenant_id=current_user.tenant_id, product_id=pid))
    
    settings = db.exec(select(Settings).where(Settings.tenant_id == current_user.tenant_id)).first()
    if settings:
        settings.is_onboarded = True
    else:
        settings = Settings(tenant_id=current_user.tenant_id, is_onboarded=True)
        db.add(settings)
        
    db.commit()
    return {"success": True, "is_onboarded": True, "products_count": len(req.product_ids)}

@router.get("/catalog")
async def get_tenant_catalog(db: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # Get active products for this tenant
    results = db.exec(
        select(Product)
        .join(TenantCatalog, TenantCatalog.product_id == Product.id)
        .where(TenantCatalog.tenant_id == current_user.tenant_id)
        .where(Product.is_deleted == False)
    ).all()
    
    # If no catalog defined, we return all by default or empty? 
    # For a new tenant who hasn't onboarded, return all so the wizard can show them.
    # Actually, the wizard step 3 should fetch `/api/v1/products` to show ALL products to select from.
    # This endpoint is for the public storefront to ONLY show selected products.
    return {"items": [r.dict() for r in results], "total": len(results)}


@router.get("/public-info")
async def get_public_store_info(db: Session = Depends(get_session)):
    settings = db.exec(select(Settings).order_by(Settings.id)).first()
    if not settings:
        return {
            "company_name": "VibeCloud",
            "logo_url": "/static/images/berelk_logo.png",
            "storefront_template": "elegante",
            "ui_theme": "standard"
        }
    return {
        "company_name": settings.company_name,
        "logo_url": settings.logo_url,
        "storefront_template": getattr(settings, "storefront_template", "elegante") or "elegante",
        "ui_theme": settings.ui_theme
    }


@router.get("/public-catalog")
async def get_public_catalog(db: Session = Depends(get_session)):
    results = db.exec(select(Product).where(Product.is_deleted == False)).all()
    return {"items": [r.model_dump() if hasattr(r, "model_dump") else r.dict() for r in results], "total": len(results)}

