"""routers/suppliers.py — Proveedores + Compras + Cuenta Corriente"""
from __future__ import annotations
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from database.models import Product, Settings, Supplier, User
from database.session import get_session
from services.purchase_service import PurchaseService
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Suppliers"])

def _templates():
    return CompatTemplates(directory="templates")

from web.pagination import paginate

@router.get("/suppliers", response_class=HTMLResponse)
def get_suppliers_page(
    request: Request, 
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user: User = Depends(require_auth), 
    settings: Settings = Depends(get_settings), 
    tenant_id: int = Depends(get_tenant), 
    session: Session = Depends(get_session)
):
    query = select(Supplier).where(Supplier.tenant_id == tenant_id).order_by(Supplier.name)
    suppliers_page = paginate(session, query, page=page, size=size)
    
    products = session.exec(select(Product).where(Product.tenant_id == tenant_id).order_by(Product.name)).all()
    balances = {s.id: PurchaseService.get_supplier_balance(session, tenant_id, s.id) for s in suppliers_page.items}
    products_catalog = [{"id": p.id, "name": p.name, "item_number": p.item_number} for p in products]
    
    return _templates().TemplateResponse("suppliers.html", {
        "request": request, 
        "active_page": "suppliers", 
        "settings": settings, 
        "user": user, 
        "suppliers": suppliers_page.items,
        "total": suppliers_page.total,
        "current_page": suppliers_page.page,
        "total_pages": suppliers_page.pages,
        "balances": balances, 
        "products": products, 
        "products_catalog": json.dumps(products_catalog)
    })

@router.get("/suppliers/{id}/account", response_class=HTMLResponse)
def get_supplier_account(id: int, request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session)):
    supplier = session.get(Supplier, id)
    if not supplier or supplier.tenant_id != tenant_id: raise HTTPException(404, "Supplier not found")
    balance = PurchaseService.get_supplier_balance(session, tenant_id, id)
    movements = PurchaseService.build_supplier_movements(session, tenant_id, id)
    return _templates().TemplateResponse("supplier_account.html", {"request": request, "active_page": "suppliers", "settings": settings, "user": user, "supplier": supplier, "balance": balance, "movements": movements})

@router.post("/api/suppliers")
def create_supplier_api(name: str = Form(...), phone: Optional[str] = Form(None), email: Optional[str] = Form(None), address: Optional[str] = Form(None), cuit: Optional[str] = Form(None), notes: Optional[str] = Form(None), session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    SettingsService.ensure_admin(user)
    return PurchaseService.create_supplier(session, tenant_id=tenant_id, name=name, phone=phone, email=email, address=address, cuit=cuit, notes=notes)

@router.put("/api/suppliers/{id}")
def update_supplier_api(id: int, name: str = Form(...), phone: Optional[str] = Form(None), email: Optional[str] = Form(None), address: Optional[str] = Form(None), cuit: Optional[str] = Form(None), notes: Optional[str] = Form(None), session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    SettingsService.ensure_admin(user)
    supplier = session.get(Supplier, id)
    if not supplier or supplier.tenant_id != tenant_id: raise HTTPException(404, "Not found")
    supplier.name, supplier.phone, supplier.email = name, phone, email
    supplier.address, supplier.cuit, supplier.notes = address, cuit, notes
    session.add(supplier)
    session.commit()
    return supplier

@router.delete("/api/suppliers/{id}")
def delete_supplier_api(id: int, session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    SettingsService.ensure_admin(user)
    supplier = session.get(Supplier, id)
    if not supplier or supplier.tenant_id != tenant_id: raise HTTPException(404, "Not found")
    session.delete(supplier)
    session.commit()
    return {"ok": True}

@router.post("/api/suppliers/{id}/pay")
def register_supplier_payment(id: int, amount: float = Form(...), note: Optional[str] = Form(None), session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    SettingsService.ensure_admin(user)
    supplier = session.get(Supplier, id)
    if not supplier or supplier.tenant_id != tenant_id: raise HTTPException(404, "Supplier not found")
    concept = f"Pago a proveedor: {supplier.name}"
    if note: concept += f" - {note}"
    PurchaseService.register_manual_cash_movement(session=session, tenant_id=tenant_id, user_id=user.id, amount=amount, movement_type="out", concept=concept, reference_id=id, reference_type="supplier_payment")
    return RedirectResponse(f"/suppliers/{id}/account", status_code=303)

class PurchaseCreateRequest(BaseModel):
    supplier_id: int
    invoice_number: Optional[str] = None
    amount_paid: float = 0.0
    items: List[dict]

@router.post("/api/purchases")
def create_purchase_api(payload: PurchaseCreateRequest, session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    SettingsService.ensure_admin(user)
    supplier = session.get(Supplier, payload.supplier_id)
    if not supplier or supplier.tenant_id != tenant_id: raise HTTPException(404, "Supplier not found")
    try:
        purchase = PurchaseService.process_purchase(session=session, user_id=user.id, tenant_id=tenant_id, supplier_id=payload.supplier_id, invoice_number=payload.invoice_number, items_data=payload.items, amount_paid=payload.amount_paid, cash_concept=f"Compra a proveedor: {supplier.name}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"status": "success", "purchase_id": purchase.id, "supplier_id": supplier.id, "redirect_url": f"/suppliers/{supplier.id}/account"}
