"""Cliente de GoDaddy (actualización 2026-08-11 -- reemplaza a NameSilo/Dynadot
como proveedor principal de venta de dominios, ver VIBECLOUD_ROADMAP_V2.md
sección "Actualización 2026-08-11").

ADVERTENCIA: este cliente sigue la API pública documentada de GoDaddy
(developer.godaddy.com/doc/endpoint/domains), pero no se probó contra la API
real porque no hay GODADDY_API_KEY/GODADDY_API_SECRET disponibles en este
entorno. Antes de usarlo en producción, probarlo con una cuenta de GoDaddy
real (entorno OTE/sandbox de GoDaddy) contra dominios de prueba.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

GODADDY_API_URL = "https://api.godaddy.com/v1/domains"


class DomainRegistrarError(Exception):
    pass


class GoDaddyClient:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("GODADDY_API_KEY", "")
        self.api_secret = api_secret or os.getenv("GODADDY_API_SECRET", "")
        if not self.api_key or not self.api_secret:
            raise DomainRegistrarError("GODADDY_API_KEY / GODADDY_API_SECRET no configuradas")

    def _headers(self) -> dict:
        # Esquema de auth propio de GoDaddy, no es Bearer estándar.
        return {
            "Authorization": f"sso-key {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{GODADDY_API_URL}{path}"
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=self._headers(), timeout=15.0, **kwargs)
            if response.status_code >= 400:
                try:
                    detail = response.json().get("message", response.text)
                except Exception:
                    detail = response.text
                raise DomainRegistrarError(f"GoDaddy API error {response.status_code}: {detail}")
            return response.json() if response.content else {}

    async def check_availability(self, domain: str) -> bool:
        data = await self._request("GET", "/available", params={"domain": domain})
        return bool(data.get("available"))

    async def register_domain(self, domain: str, years: int = 1, contact: Optional[dict] = None) -> dict:
        """
        GoDaddy exige datos de contacto reales (registrant/admin/billing/tech)
        para comprar un dominio -- no hay forma de comprarlo solo con
        dominio+años como con NameSilo. `contact` puede pasar overrides; si no
        se pasa nada, se arma desde variables de entorno GODADDY_CONTACT_*
        (mismo contacto para los 4 roles, caso común de una sola empresa
        dueña de todos los dominios que compra la plataforma).
        """
        contact_info = contact or self._default_contact_from_env()
        payload = {
            "domain": domain,
            "period": years,
            "privacy": True,
            "renewAuto": False,
            "consent": {
                "agreementKeys": ["DNRA"],
                "agreedBy": contact_info.get("email", ""),
                "agreedAt": _now_iso(),
            },
            "contactAdmin": contact_info,
            "contactBilling": contact_info,
            "contactRegistrant": contact_info,
            "contactTech": contact_info,
        }
        data = await self._request("POST", "/purchase", json=payload)
        return {"domain": domain, "order_id": str(data.get("orderId", ""))}

    @staticmethod
    def _default_contact_from_env() -> dict:
        required = {
            "nameFirst": os.getenv("GODADDY_CONTACT_FIRST_NAME", ""),
            "nameLast": os.getenv("GODADDY_CONTACT_LAST_NAME", ""),
            "email": os.getenv("GODADDY_CONTACT_EMAIL", ""),
            "phone": os.getenv("GODADDY_CONTACT_PHONE", ""),
            "addressMailing": {
                "address1": os.getenv("GODADDY_CONTACT_ADDRESS", ""),
                "city": os.getenv("GODADDY_CONTACT_CITY", ""),
                "state": os.getenv("GODADDY_CONTACT_STATE", ""),
                "postalCode": os.getenv("GODADDY_CONTACT_POSTAL_CODE", ""),
                "country": os.getenv("GODADDY_CONTACT_COUNTRY", ""),
            },
        }
        missing = [k for k, v in required.items() if k != "addressMailing" and not v]
        if missing:
            raise DomainRegistrarError(
                f"Faltan variables de entorno de contacto para comprar dominios en GoDaddy: {', '.join(missing)}"
            )
        return required


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_verification_txt_record_name(domain: str) -> str:
    return f"_vibecloud-verify.{domain}"


async def verify_domain_txt(domain: str, expected_token: str) -> bool:
    """
    Busca un registro TXT en _vibecloud-verify.<dominio> que contenga el
    token esperado. Requiere dnspython (agregado a requirements.txt).
    Devuelve False (no True) si dnspython no está instalado o si la
    consulta DNS falla -- nunca marca un dominio como verificado por error.
    """
    try:
        import dns.resolver
    except ImportError:
        return False

    record_name = get_verification_txt_record_name(domain)
    try:
        answers = dns.resolver.resolve(record_name, "TXT")
    except Exception:
        return False

    for rdata in answers:
        value = b"".join(rdata.strings).decode("utf-8", errors="ignore") if hasattr(rdata, "strings") else str(rdata)
        if expected_token in value:
            return True
    return False
