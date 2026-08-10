"""Cliente de NameSilo (Fase 5 del roadmap, decisión confirmada: arrancar con
NameSilo o Dynadot -- ver VIBECLOUD_ROADMAP_V2.md sección 4.6).

ADVERTENCIA: este cliente sigue la API pública documentada de NameSilo
(namesilo.com/api-reference), pero no se probó contra la API real porque
no hay una NAMESILO_API_KEY disponible en este entorno. Antes de usarlo en
producción, probarlo con una cuenta de NameSilo real (sandbox si está
disponible) contra dominios de prueba.
"""
from __future__ import annotations

import os
from xml.etree import ElementTree

import httpx

NAMESILO_API_URL = "https://www.namesilo.com/api"


class DomainRegistrarError(Exception):
    pass


class NameSiloClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("NAMESILO_API_KEY", "")
        if not self.api_key:
            raise DomainRegistrarError("NAMESILO_API_KEY no configurada")

    async def _call(self, operation: str, params: dict) -> ElementTree.Element:
        query = {"version": "1", "type": "xml", "key": self.api_key, **params}
        url = f"{NAMESILO_API_URL}/{operation}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=query, timeout=15.0)
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
            code_el = root.find(".//reply/code")
            if code_el is not None and code_el.text != "300":
                detail_el = root.find(".//reply/detail")
                raise DomainRegistrarError(
                    f"NameSilo API error {code_el.text}: {detail_el.text if detail_el is not None else ''}"
                )
            return root

    async def check_availability(self, domain: str) -> bool:
        root = await self._call("checkRegisterAvailability", {"domains": domain})
        available = root.find(".//reply/available")
        return available is not None and len(list(available)) > 0

    async def register_domain(self, domain: str, years: int = 1) -> dict:
        root = await self._call("registerDomain", {"domain": domain, "years": str(years), "private": "1"})
        return {"domain": domain, "order_id": (root.findtext(".//reply/order") or "")}


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
