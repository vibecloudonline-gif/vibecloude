from fastapi import APIRouter, Depends, HTTPException, Header, Response
from sqlmodel import Session
from database.session import get_session
from database.models import ProcessedWebhook
from pydantic import BaseModel
from typing import Optional, List
from core.config import settings
from services.stock_service import StockService

router = APIRouter()
stock_service = StockService()

class WebhookItem(BaseModel):
    product_id: str
    quantity: int

class DeductOrderRequest(BaseModel):
    id: str  # event_id del webhook
    order_id: str
    source: str = "medusa_storefront"
    items: List[WebhookItem]

@router.post("/deduct-from-order")
def deduct_from_order(
    request: DeductOrderRequest,
    x_api_key: Optional[str] = Header(None),
    session: Session = Depends(get_session)
):
    if not x_api_key or x_api_key != settings.MEDUSA_ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
        
    event_id = request.id
    tenant_id = 1  # Por defecto para este flujo
    
    # Idempotency Check
    existing = session.get(ProcessedWebhook, event_id)
    if existing:
        return Response(status_code=200, content="Already processed (idempotent)")
    
    # Iniciar transacción para deducción y guardado de log
    try:
        for item in request.items:
            # Intentar convertir product_id a int si el backend lo requiere como numérico
            try:
                p_id = int(item.product_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid product_id: {item.product_id}")
                
            # Descontar stock usando StockService (restar cantidad, se pasa como valor negativo a add_stock)
            stock_service.add_stock(
                session=session,
                product_id=p_id,
                tenant_id=tenant_id,
                quantity=-item.quantity,
                reason="venta",
                notes=f"Descuento automático Webhook Orden {request.order_id}"
            )
            
        webhook_log = ProcessedWebhook(
            event_id=event_id,
            source=request.source,
            status="processed"
        )
        session.add(webhook_log)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error al procesar el inventario: {str(e)}")
    
    return {"status": "success", "order_id": request.order_id}

