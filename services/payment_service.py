"""services/payment_service.py — Pasarelas de pago (PayPal, Stripe, +MercadoPago futuro).

Patrón provider: cada pasarela implementa PaymentProvider. PaymentService
elige el provider según el nombre y delega. Agregar MercadoPago es escribir
una clase nueva + registrarla en PROVIDERS, sin tocar routers ni lógica.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PaymentResult:
    external_id: str
    approve_url: str
    status: str
    raw: dict


@dataclass
class CaptureResult:
    external_id: str
    status: str
    raw: dict


class PaymentProvider(ABC):
    @abstractmethod
    async def create_order(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        ...

    @abstractmethod
    async def capture_order(self, external_id: str) -> CaptureResult:
        ...

    @abstractmethod
    def verify_webhook(self, headers: dict, body: bytes) -> Optional[dict]:
        ...


class PayPalProvider(PaymentProvider):
    SANDBOX_URL = "https://api-m.sandbox.paypal.com"
    LIVE_URL = "https://api-m.paypal.com"

    def __init__(self) -> None:
        self.client_id = os.getenv("PAYPAL_CLIENT_ID", "")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
        mode = os.getenv("PAYPAL_MODE", "sandbox").lower()
        self.base_url = self.LIVE_URL if mode == "live" else self.SANDBOX_URL
        self._access_token: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            return self._access_token

    async def _headers(self) -> dict:
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def create_order(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency,
                        "value": str(amount),
                    },
                    "description": description[:127],
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                        "user_action": "PAY_NOW",
                    }
                }
            },
        }
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                json=payload,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()

        data = resp.json()
        approve_url = ""
        for link in data.get("links", []):
            if link.get("rel") == "payer-action":
                approve_url = link["href"]
                break

        return PaymentResult(
            external_id=data["id"],
            approve_url=approve_url,
            status=data.get("status", "CREATED"),
            raw=data,
        )

    async def capture_order(self, external_id: str) -> CaptureResult:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/checkout/orders/{external_id}/capture",
                headers=headers,
                json={},
                timeout=15,
            )
            resp.raise_for_status()

        data = resp.json()
        return CaptureResult(
            external_id=data["id"],
            status=data.get("status", ""),
            raw=data,
        )

    def verify_webhook(self, headers: dict, body: bytes) -> Optional[dict]:
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None


class StripeProvider(PaymentProvider):
    def __init__(self) -> None:
        self.secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    def is_configured(self) -> bool:
        return bool(self.secret_key)

    async def create_order(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        amount_cents = int(amount * 100)
        payload = {
            "mode": "payment",
            "payment_method_types[]": "card",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][price_data][product_data][name]": description[:250],
            "line_items[0][quantity]": "1",
            "success_url": return_url,
            "cancel_url": cancel_url,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload,
                auth=(self.secret_key, ""),
                timeout=15,
            )
            resp.raise_for_status()

        data = resp.json()
        return PaymentResult(
            external_id=data["id"],
            approve_url=data.get("url", ""),
            status=data.get("status", "open"),
            raw=data,
        )

    async def capture_order(self, external_id: str) -> CaptureResult:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{external_id}",
                auth=(self.secret_key, ""),
                timeout=15,
            )
            resp.raise_for_status()

        data = resp.json()
        return CaptureResult(
            external_id=data["id"],
            status="COMPLETED" if data.get("payment_status") == "paid" else data.get("status", ""),
            raw=data,
        )

    def verify_webhook(self, headers: dict, body: bytes) -> Optional[dict]:
        if not self.webhook_secret:
            return None
        import hmac
        import hashlib
        import time

        sig_header = headers.get("stripe-signature", "")
        pairs = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        timestamp = pairs.get("t", "")
        signature = pairs.get("v1", "")
        if not timestamp or not signature:
            return None

        try:
            ts = int(timestamp)
        except ValueError:
            return None
        if abs(time.time() - ts) > 300:
            return None

        signed_payload = f"{timestamp}.{body.decode('utf-8')}"
        expected = hmac.HMAC(
            self.webhook_secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            return None
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None


PROVIDERS: dict[str, PaymentProvider] = {}

def _init_providers() -> None:
    paypal = PayPalProvider()
    if paypal.is_configured():
        PROVIDERS["paypal"] = paypal
    stripe = StripeProvider()
    if stripe.is_configured():
        PROVIDERS["stripe"] = stripe

_init_providers()


def get_provider(name: str) -> PaymentProvider:
    provider = PROVIDERS.get(name)
    if not provider:
        available = list(PROVIDERS.keys())
        raise ValueError(
            f"Provider '{name}' no configurado. Disponibles: {available}"
        )
    return provider


def get_available_providers() -> list[str]:
    return list(PROVIDERS.keys())
