import asyncio
import os
import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="Requires a live API server on localhost:8000",
)

async def test_webhook():
    url = "http://localhost:8000/api/v1/inventory/deduct-from-order"
    headers = {"x-api-key": "fake_key_test"}
    payload = {"order_id": "order_123", "source": "medusa_storefront"}
    
    async with httpx.AsyncClient() as client:
        print("Sending first webhook...")
        resp1 = await client.post(url, json=payload, headers=headers)
        print("Response 1:", resp1.status_code, resp1.text)
        
        print("Sending duplicate webhook...")
        resp2 = await client.post(url, json=payload, headers=headers)
        print("Response 2:", resp2.status_code, resp2.text)

if __name__ == "__main__":
    asyncio.run(test_webhook())
