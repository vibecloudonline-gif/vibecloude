import asyncio
import httpx
from core.config import settings

async def create_b2b_customer():
    print("Creando cliente B2B Wholesale...")
    
    headers = {
        "Authorization": f"Bearer {settings.MEDUSA_ADMIN_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        # 1. Crear cliente
        print("1. Registrando b2b@vibecloud.com...")
        customer_resp = await client.post(
            f"{settings.MEDUSA_URL}/admin/customers",
            headers=headers,
            json={
                "email": "b2b@vibecloud.com",
                "first_name": "VibeCloud",
                "last_name": "Wholesale"
            }
        )
        
        if customer_resp.status_code not in (200, 201):
            if "already exists" in customer_resp.text:
                print("El cliente ya existe, obteniendo ID...")
                search = await client.get(
                    f"{settings.MEDUSA_URL}/admin/customers?q=b2b@vibecloud.com",
                    headers=headers
                )
                customer_id = search.json()["customers"][0]["id"]
            else:
                print("Error creando cliente:", customer_resp.text)
                return
        else:
            customer_id = customer_resp.json()["customer"]["id"]
            
        print(f"Cliente ID: {customer_id}")

        # 2. Buscar Customer Group 'Wholesale'
        groups_resp = await client.get(
            f"{settings.MEDUSA_URL}/admin/customer-groups?q=Wholesale",
            headers=headers
        )
        groups = groups_resp.json().get("customer_groups", [])
        wholesale = next((g for g in groups if g["name"] == "Wholesale"), None)
        
        if not wholesale:
            print("❌ El grupo Wholesale no existe. Asegúrate de haber sincronizado al menos un producto con price_bulk desde VibeCloud.")
            return

        group_id = wholesale["id"]
        print(f"Grupo Wholesale ID: {group_id}")

        # 3. Asignar cliente al grupo
        print("3. Asignando cliente al grupo B2B...")
        add_resp = await client.post(
            f"{settings.MEDUSA_URL}/admin/customer-groups/{group_id}/customers",
            headers=headers,
            json={"customer_ids": [{"id": customer_id}]}
        )
        
        if add_resp.status_code == 200:
            print("✅ ¡Éxito! Ahora puedes iniciar sesión en el Storefront con b2b@vibecloud.com (crea la contraseña en el storefront) y verás el 30% de descuento automático.")
        else:
            print("Error asignando grupo:", add_resp.text)

if __name__ == "__main__":
    asyncio.run(create_b2b_customer())
