"""services/crm_service.py — Sync bidireccional con CRM externo via REST"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import httpx
from sqlmodel import Session, select
from database.models import (
    Client, Sale, SaleItem, AICredential, Settings, CRMSyncLog,
    decrypt_api_key,
)

logger = logging.getLogger(__name__)


class CRMSyncService:

    def __init__(self, session: Session, tenant_id: int, base_url: str, api_key: str):
        self.session = session
        self.tenant_id = tenant_id
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def from_tenant(cls, session: Session, tenant_id: int) -> Optional["CRMSyncService"]:
        cred = session.exec(
            select(AICredential).where(
                AICredential.tenant_id == tenant_id,
                AICredential.provider == "crm",
            )
        ).first()
        if not cred:
            return None
        try:
            api_key = decrypt_api_key(cred.api_key_enc)
        except Exception:
            logger.error("Failed to decrypt CRM API key for tenant %s", tenant_id)
            return None
        import json
        settings = session.exec(
            select(Settings).where(Settings.tenant_id == tenant_id)
        ).first()
        base_url = ""
        if settings and settings.site_config_json:
            try:
                cfg = json.loads(settings.site_config_json) if isinstance(settings.site_config_json, str) else settings.site_config_json
                base_url = cfg.get("crm_base_url", "")
            except Exception:
                pass
        if not base_url:
            return None
        return cls(session, tenant_id, base_url, api_key)

    def _log(self, sync_type: str, direction: str) -> CRMSyncLog:
        log = CRMSyncLog(
            tenant_id=self.tenant_id,
            sync_type=sync_type,
            direction=direction,
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return log

    def _finish_log(self, log: CRMSyncLog, status: str, errors: str = None):
        log.status = status
        log.finished_at = datetime.now(timezone.utc)
        if errors:
            log.errors = errors
        self.session.add(log)
        self.session.commit()

    def pull_contacts(self) -> CRMSyncLog:
        log = self._log("contacts", "pull")
        errors = []
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(f"{self.base_url}/api/contacts", headers=self.headers)
                resp.raise_for_status()
                contacts = resp.json()
                if isinstance(contacts, dict):
                    contacts = contacts.get("data", contacts.get("results", []))
                count = 0
                for c in contacts:
                    ext_id = str(c.get("id", ""))
                    if not ext_id:
                        continue
                    existing = self.session.exec(
                        select(Client).where(
                            Client.tenant_id == self.tenant_id,
                            Client.crm_external_id == ext_id,
                        )
                    ).first()
                    if existing:
                        existing.name = c.get("name", existing.name)
                        existing.email = c.get("email", existing.email)
                        existing.phone = c.get("phone", existing.phone)
                        self.session.add(existing)
                    else:
                        new_client = Client(
                            tenant_id=self.tenant_id,
                            name=c.get("name", "Sin nombre"),
                            email=c.get("email"),
                            phone=c.get("phone"),
                            crm_external_id=ext_id,
                        )
                        self.session.add(new_client)
                    count += 1
                self.session.commit()
                log.contacts_synced = count
                self._finish_log(log, "completed")
        except httpx.HTTPStatusError as e:
            errors.append(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
            self._finish_log(log, "error", "\n".join(errors))
        except Exception as e:
            errors.append(str(e)[:300])
            self._finish_log(log, "error", "\n".join(errors))
        return log

    def push_contacts(self) -> CRMSyncLog:
        log = self._log("contacts", "push")
        errors = []
        try:
            clients = self.session.exec(
                select(Client).where(
                    Client.tenant_id == self.tenant_id,
                    Client.is_deleted == False,
                )
            ).all()
            count = 0
            with httpx.Client(timeout=30) as client:
                for cl in clients:
                    payload = {
                        "name": cl.name,
                        "email": cl.email,
                        "phone": cl.phone,
                        "external_id": str(cl.id),
                    }
                    if cl.crm_external_id:
                        resp = client.put(
                            f"{self.base_url}/api/contacts/{cl.crm_external_id}",
                            json=payload, headers=self.headers,
                        )
                    else:
                        resp = client.post(
                            f"{self.base_url}/api/contacts",
                            json=payload, headers=self.headers,
                        )
                    if resp.status_code < 300:
                        data = resp.json()
                        new_id = str(data.get("id", ""))
                        if new_id and not cl.crm_external_id:
                            cl.crm_external_id = new_id
                            self.session.add(cl)
                        count += 1
                    else:
                        errors.append(f"Contact {cl.id}: HTTP {resp.status_code}")
            self.session.commit()
            log.contacts_synced = count
            self._finish_log(log, "completed" if not errors else "partial", "\n".join(errors) if errors else None)
        except Exception as e:
            errors.append(str(e)[:300])
            self._finish_log(log, "error", "\n".join(errors))
        return log

    def push_sales(self) -> CRMSyncLog:
        log = self._log("sales", "push")
        errors = []
        try:
            sales = self.session.exec(
                select(Sale).where(
                    Sale.tenant_id == self.tenant_id,
                    Sale.crm_external_id == None,
                ).order_by(Sale.timestamp.desc()).limit(100)
            ).all()
            count = 0
            with httpx.Client(timeout=30) as client:
                for sale in sales:
                    payload = {
                        "external_id": str(sale.id),
                        "total": float(sale.total_amount),
                        "status": sale.payment_status,
                        "date": sale.timestamp.isoformat(),
                        "client_external_id": sale.client.crm_external_id if sale.client else None,
                    }
                    resp = client.post(
                        f"{self.base_url}/api/deals",
                        json=payload, headers=self.headers,
                    )
                    if resp.status_code < 300:
                        data = resp.json()
                        sale.crm_external_id = str(data.get("id", ""))
                        self.session.add(sale)
                        count += 1
                    else:
                        errors.append(f"Sale {sale.id}: HTTP {resp.status_code}")
            self.session.commit()
            log.sales_synced = count
            self._finish_log(log, "completed" if not errors else "partial", "\n".join(errors) if errors else None)
        except Exception as e:
            errors.append(str(e)[:300])
            self._finish_log(log, "error", "\n".join(errors))
        return log

    def full_sync(self) -> CRMSyncLog:
        log = self._log("full", "bidirectional")
        errors = []
        try:
            pull_log = self.pull_contacts()
            push_log = self.push_contacts()
            sales_log = self.push_sales()
            log.contacts_synced = pull_log.contacts_synced + push_log.contacts_synced
            log.sales_synced = sales_log.sales_synced
            all_errors = []
            for l in [pull_log, push_log, sales_log]:
                if l.errors:
                    all_errors.append(l.errors)
            status = "completed"
            if any(l.status == "error" for l in [pull_log, push_log, sales_log]):
                status = "error"
            elif any(l.status == "partial" for l in [pull_log, push_log, sales_log]):
                status = "partial"
            self._finish_log(log, status, "\n".join(all_errors) if all_errors else None)
        except Exception as e:
            self._finish_log(log, "error", str(e)[:500])
        return log
