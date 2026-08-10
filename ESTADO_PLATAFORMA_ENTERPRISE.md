# Estado Técnico: VibeCloud Enterprise (B2B / B2C)

A continuación se detalla el estado actual de la plataforma híbrida VibeCloud, luego de haber completado las fases de sincronización bidireccional, inyección SDUI, autenticación y *rebranding* global.

## 1. Arquitectura General (Híbrida)
El sistema está compuesto por dos "cerebros" conectados a una única base de datos Supabase (PostgreSQL):
- **Cerebro Operativo (Python/FastAPI):** Núcleo de VibeCloud SaaS. Maneja el Backoffice, inventario complejo (BinStock), IA (Google Gemini), y configuración de Server-Driven UI (SDUI).
- **Motor E-commerce (Node.js/MedusaJS v2):** Maneja los carritos, checkout, pasarelas de pago y lógica de precios dinámicos (Price Lists y Customer Groups).
- **Storefront B2C/B2B (Next.js):** Interfaz pública que lee el catálogo de Medusa y recibe su diseño/colores desde Python.

## 2. Flujo de Datos B2B (Mayorista)
El flujo mayorista se ha cerrado con éxito:
1. **Creación de Productos:** Cuando se crea un producto en Python, el servicio `medusa_sync_service.py` empuja el producto a Medusa.
2. **Precios B2B (`price_bulk`):** El sincronizador automáticamente inyecta el `price_bulk` dentro de una **Price List (B2B)** en Medusa usando el motor de reglas de Medusa v2.
3. **Autenticación (Customer Groups):** Los clientes etiquetados en el *Customer Group* `Wholesale` obtienen automáticamente el precio rebajado (30%) en el Storefront de Next.js al iniciar sesión. MedusaJS inyecta el contexto del usuario en la sesión, por lo que el frontend no necesita código extra para calcular precios.

## 3. Server-Driven UI (SDUI)
- **API Híbrida:** El frontend de Next.js (`storefront/`) ahora hace una llamada SSR a `GET /api/v1/ui-config/public/{tenant}/{page}` en el backend de Python.
- **Inyección Global CSS:** Extrae los colores (`primary_color`, `secondary_color`) definidos por el administrador (o generados por Gemini) y los inyecta como variables CSS (`--primary-sdui`) en el tag `<html>` de Next.js.
- **Glassmorphism:** Componentes clave como el `Nav` han sido actualizados en Next.js para usar Tailwind con soporte de desenfoque (`backdrop-blur-md`) y sombras de neón usando las variables de Python.

## 4. Cola de Sincronización y Tolerancia a Fallos
- **SyncQueue:** Cualquier fallo de red al sincronizar hacia Medusa guarda un registro en la tabla `sync_queue` de Supabase.
- **Background Worker:** El script `workers/sync_queue_worker.py` corre cada 5 minutos, retomando los intentos fallidos a través del Singleton `MedusaSyncService`.

## 5. Infraestructura y Despliegue (Render)
El archivo `render.yaml` está configurado para un ecosistema de 5 servicios:
1. `vibecloud-api` (FastAPI)
2. `vibecloud-worker` (Background jobs)
3. `vibecloud-medusa` (Node.js backend)
4. `vibecloud-storefront` (Next.js)
5. `vibecloud-redis` (Caché y colas)

> **Rebranding Finalizado:** Se ha ejecutado un script de limpieza global que renombró todas las menciones a `VibeCloud`. Deberás actualizar los *Environment Secrets* en Render (ej. usar `VIBECLOUD_API_KEY`) la próxima vez que se despliegue.

## Siguientes Pasos (Roadmap Enterprise)
La plataforma base está 100% operativa. Los siguientes pasos recomendados para pasar a producción a gran escala son:
1. **Poblar la Base de Datos:** Ejecutar los scripts de importación de `clientes.xlsx` y `productos.xlsx` en el backend de Python para desencadenar la sincronización masiva a Medusa.
2. **Configuración de Pasarelas de Pago:** Activar Stripe/MercadoPago dentro del administrador de Medusa.
3. **Mapeo de Dominios:** Conectar el dominio final de VibeCloud a los endpoints en Render.
