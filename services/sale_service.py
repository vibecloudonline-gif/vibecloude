"""services/sale_service.py — Lógica de ventas y reportes diarios"""
from __future__ import annotations
from collections import defaultdict
from typing import List, Dict, Any
from sqlmodel import Session, select
from database.models import Sale

class SaleService:
    @staticmethod
    def build_daily_reports(session: Session, tenant_id: int, open_only: bool = True) -> List[Dict[str, Any]]:
        """Agrupa ventas por día para reportes en el listado de ventas."""
        query = select(Sale).where(Sale.tenant_id == tenant_id)
        if open_only:
            query = query.where(Sale.is_closed == False)
        
        sales = session.exec(query.order_by(Sale.timestamp.desc())).all()
        
        daily_groups = defaultdict(list)
        for sale in sales:
            date_str = sale.timestamp.strftime('%Y-%m-%d')
            daily_groups[date_str].append(sale)
            
        reports = [
            {
                "date": d,
                "total": sum(s.total_amount for s in ds),
                "sales": ds
            } for d, ds in daily_groups.items()
        ]
        reports.sort(key=lambda x: x['date'], reverse=True)
        return reports
