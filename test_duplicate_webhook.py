"""
test_duplicate_webhook.py

Simula que Medusa envia el MISMO webhook dos veces y verifica que
VibeCloud solo lo procesa una vez.

Uso:
    python test_duplicate_webhook.py
"""

import asyncio
import os
import sys
import uuid

import httpx

# ── Config ────────────────────────────────────────────────────────
NEXPOS_BASE_URL = os.getenv("NEXPOS_BASE_URL", "http://localhost:8000")
NEXPOS_API_KEY = os.getenv("NEXPOS_API_KEY", "")
TEST_PRODUCT_ID = os.getenv("TEST_PRODUCT_ID", "1")

WEBHOOK_PATH = "/api/v1/inventory/deduct-from-order"

# Opcional: si tienen un endpoint de consulta de producto/stock
STOCK_CHECK_PATH = os.getenv("STOCK_CHECK_PATH", "")

# Palabras clave a buscar en la respuesta del duplicado
DUPLICATE_MARKERS = ["already processed", "already_processed", "idempotent", "duplicate"]


async def send_webhook(client: httpx.AsyncClient, event_id: str, quantity: int = 1) -> httpx.Response:
    payload = {
        "id": event_id,               # simula el id de evento de Medusa
        "order_id": f"order_test_{event_id[:8]}",
        "source": "medusa_storefront",
        "items": [
            {"product_id": TEST_PRODUCT_ID, "quantity": quantity}
        ],
    }
    headers = {"x-api-key": NEXPOS_API_KEY} if NEXPOS_API_KEY else {}
    return await client.post(WEBHOOK_PATH, json=payload, headers=headers)


async def get_stock(client: httpx.AsyncClient) -> int | None:
    if not STOCK_CHECK_PATH:
        return None
    try:
        path = STOCK_CHECK_PATH.format(id=TEST_PRODUCT_ID)
        resp = await client.get(path)
        resp.raise_for_status()
        data = resp.json()
        return data.get("stock_quantity", data.get("stock", data.get("quantity")))
    except Exception:
        return None


async def run() -> None:
    print("== Test de idempotencia: webhook duplicado ==")
    print("Target: {}{}\n".format(NEXPOS_BASE_URL, WEBHOOK_PATH))

    if not NEXPOS_API_KEY:
        print("[WARNING] NEXPOS_API_KEY no seteada - el request puede fallar por auth (401/403).")
        print("Exportala si tu endpoint la requiere.\n")

    async with httpx.AsyncClient(base_url=NEXPOS_BASE_URL, timeout=15.0) as client:
        stock_before = await get_stock(client)
        if stock_before is not None:
            print("Stock inicial de {}: {}".format(TEST_PRODUCT_ID, stock_before))

        # 1. Primer envio - debe procesarse normalmente
        event_id = str(uuid.uuid4())
        print("Enviando webhook por primera vez (event_id={})...".format(event_id))
        resp1 = await send_webhook(client, event_id, quantity=1)
        print("      -> status {} | body: {}".format(resp1.status_code, resp1.text[:200]))

        if resp1.status_code not in (200, 201):
            print("\n[ERROR] El primer envio ya fallo ({}).".format(resp1.status_code))
            print("Revisa NEXPOS_API_KEY / TEST_PRODUCT_ID antes de seguir.")
            sys.exit(1)

        # 2. Reenviar EXACTAMENTE el mismo event_id (simula reintento/duplicado)
        print("Reenviando el MISMO webhook (event_id={})...".format(event_id))
        resp2 = await send_webhook(client, event_id, quantity=1)
        print("      -> status {} | body: {}".format(resp2.status_code, resp2.text[:200]))

        body2_lower = resp2.text.lower()
        detected_as_duplicate = any(marker in body2_lower for marker in DUPLICATE_MARKERS)

        # 3. Verificacion
        print("\nResultado:")
        if resp2.status_code == 200 and detected_as_duplicate:
            print("SUCCESS: IDEMPOTENCIA OK - el segundo envio fue reconocido como duplicado")
            print("y no deberia haber tocado el stock de nuevo.")
        elif resp2.status_code == resp1.status_code and not detected_as_duplicate:
            print("WARNING: El segundo envio devolvio el MISMO status que el primero pero")
            print("el cuerpo NO menciona duplicado/idempotencia. Esto es sospechoso:")
            print("puede que se haya procesado dos veces. Revisar manualmente en DB")
            print("la tabla processed_webhooks y el stock real del producto.")
        else:
            print("ERROR: Respuesta inesperada en el duplicado (status {}).".format(resp2.status_code))
            print("Revisar el handler - puede estar fallando en vez de detectar el duplicado.")

        stock_after = await get_stock(client)
        if stock_before is not None and stock_after is not None:
            print("\nStock: {} -> {}".format(stock_before, stock_after))
            if stock_after == stock_before - 1:
                print("SUCCESS: Confirmado tambien por stock: se desconto una sola vez.")
            elif stock_after == stock_before - 2:
                print("ERROR: BUG CONFIRMADO POR STOCK: se desconto DOS veces.")
                sys.exit(1)
            else:
                print("WARNING: Delta de stock no coincide con lo esperado, revisar manualmente.")
        elif not STOCK_CHECK_PATH:
            print("\n(No se configuro STOCK_CHECK_PATH - validacion basada solo en la")
            print("respuesta del endpoint, no en el stock real. Para el chequeo completo,")
            print("setea esa variable si existe un endpoint de consulta de producto.)")


if __name__ == "__main__":
    asyncio.run(run())
