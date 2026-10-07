"""services/payment_service.py — Pasarelas de pago (Mercado Pago, Stripe, PayPal).

Patrón provider: cada pasarela implementa PaymentProvider. Se elige por nombre
y se delega. El checkout del storefront usa las credenciales DEL COMERCIO
(TenantPaymentConfig), nunca las de la plataforma.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PaymentResult:
    external_id: str
    approve_url: str
    status: str
    raw: dict = field(default_factory=dict)


@dataclass
class CaptureResult:
    external_id: str
    status: str  # "COMPLETED", "PENDING", "FAILED", etc.
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    raw: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    @abstractmethod
    async def create_order(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        cancel_url: str,
        *,
        external_ref: str = "",
        merchant_token: str = "",
        commission_amount: Decimal = Decimal("0"),
    ) -> PaymentResult:
        ...

    @abstractmethod
    async def capture_order(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
        ...

    @abstractmethod
    async def get_payment_info(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
        ...

    @abstractmethod
    def verify_webhook(self, headers: dict, body: bytes) -> Optional[dict]:
        ...


# ── Mercado Pago ──────────────────────────────────────────────────────────

class MercadoPagoProvider(PaymentProvider):
    """Mercado Pago Checkout Pro con marketplace_fee."""
    BASE_URL = "https://api.mercadopago.com"

    def __init__(self) -> None:
        self.platform_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
        self.webhook_secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "")

    def is_configured(self) -> bool:
        return bool(self.platform_token)

    def _token(self, merchant_token: str) -> str:
        return merchant_token or self.platform_token

    async def create_order(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        return_url: str,
        cancel_url: str,
        *,
        external_ref: str = "",
        merchant_token: str = "",
        commission_amount: Decimal = Decimal("0"),
    ) -> PaymentResult:
        token = self._token(merchant_token)
        payload: dict = {
            "items": [{
                "title": description[:256],
                "quantity": 1,
                "unit_price": float(amount),
                "currency_id": currency,
            }],
            "back_urls": {
                "success": return_url,
                "failure": cancel_url,
                "pending": return_url,
            },
            "auto_return": "approved",
            "notification_url": os.getenv("VIBECLOUD_WEBHOOK_URL_MP", ""),
        }
        if external_ref:
            payload["external_reference"] = external_ref
        if commission_amount > 0 and merchant_token:
            payload["marketplace_fee"] = float(commission_amount)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/checkout/preferences",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()

        data = resp.json()
        init_point = data.get("sandbox_init_point") or data.get("init_point", "")
        return PaymentResult(
            external_id=data["id"],
            approve_url=init_point,
            status="created",
            raw=data,
        )

    async def capture_order(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
        return await self.get_payment_info(external_id, merchant_token=merchant_token)

    async def get_payment_info(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
        token = self._token(merchant_token)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/v1/payments/{external_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()

        data = resp.json()
        mp_status = data.get("status", "")
        status_map = {
            "approved": "COMPLETED",
            "authorized": "COMPLETED",
            "pending": "PENDING",
            "in_process": "PENDING",
            "rejected": "FAILED",
            "cancelled": "CANCELLED",
            "refunded": "REFUNDED",
            "charged_back": "CHARGED_BACK",
        }
        return CaptureResult(
            external_id=str(data.get("id", external_id)),
            status=status_map.get(mp_status, mp_status.upper()),
            amount=Decimal(str(data.get("transaction_amount", 0))),
            currency=data.get("currency_id", ""),
            raw=data,
        )

    def verify_webhook(self, headers: dict, body: bytes) -> Optional[dict]:
        if not self.webhook_secret:
            try:
                return json.loads(body)
            except (json.JSONDecodeError, ValueError):
                return None

        x_signature = headers.get("x-signature", "")
        x_request_id = headers.get("x-request-id", "")

        parts = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
        ts = parts.get("ts", "")
        v1 = parts.get("v1", "")
        if not ts or not v1:
            return None

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None

        data_id = str(payload.get("data", {}).get("id", ""))
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        expected = hmac.HMAC(
            self.webhook_secret.encode(),
            manifest.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, v1):
            logger.warning("MP webhook signature mismatch")
            return None
        return payload


# ── Stripe ────────────────────────────────────────────────────────────────

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
        *,
        external_ref: str = "",
        merchant_token: str = "",
        commission_amount: Decimal = Decimal("0"),
    ) -> PaymentResult:
        amount_cents = int(amount * 100)
        payload: dict = {
            "mode": "payment",
            "payment_method_types[]": "card",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][price_data][product_data][name]": description[:250],
            "line_items[0][quantity]": "1",
            "success_url": return_url,
            "cancel_url": cancel_url,
        }
        if external_ref:
            payload["client_reference_id"] = external_ref
        if commission_amount > 0 and merchant_token:
            payload["payment_intent_data[application_fee_amount]"] = str(int(commission_amount * 100))
            payload["payment_intent_data[transfer_data][destination]"] = merchant_token

        auth_key = merchant_token if merchant_token and not commission_amount else self.secret_key
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload,
                auth=(auth_key or self.secret_key, ""),
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

    async def capture_order(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
        return await self.get_payment_info(external_id, merchant_token=merchant_token)

    async def get_payment_info(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{external_id}",
                auth=(self.secret_key, ""),
                timeout=15,
            )
            resp.raise_for_status()

        data = resp.json()
        status = "COMPLETED" if data.get("payment_status") == "paid" else data.get("status", "").upper()
        return CaptureResult(
            external_id=data["id"],
            status=status,
            amount=Decimal(str(data.get("amount_total", 0))) / 100 if data.get("amount_total") else None,
            currency=data.get("currency", "").upper(),
            raw=data,
        )

    def verify_webhook(self, headers: dict, body: bytes) -> Optional[dict]:
        if not self.webhook_secret:
            return None

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


# ── PayPal ────────────────────────────────────────────────────────────────

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
        *,
        external_ref: str = "",
        merchant_token: str = "",
        commission_amount: Decimal = Decimal("0"),
    ) -> PaymentResult:
        payload: dict = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": currency,
                    "value": str(amount),
                },
                "description": description[:127],
            }],
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
        if external_ref:
            payload["purchase_units"][0]["custom_id"] = external_ref

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

    async def capture_order(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
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

    async def get_payment_info(self, external_id: str, *, merchant_token: str = "") -> CaptureResult:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v2/checkout/orders/{external_id}",
                headers=headers,
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


# ── Registry ──────────────────────────────────────────────────────────────

PROVIDERS: dict[str, PaymentProvider] = {}


def _init_providers() -> None:
    mp = MercadoPagoProvider()
    if mp.is_configured():
        PROVIDERS["mercadopago"] = mp
    stripe = StripeProvider()
    if stripe.is_configured():
        PROVIDERS["stripe"] = stripe
    paypal = PayPalProvider()
    if paypal.is_configured():
        PROVIDERS["paypal"] = paypal


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
