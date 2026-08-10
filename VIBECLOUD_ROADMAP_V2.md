# VibeCloud — Plan de Implementación v2: Hosting Provider (ERP B2B + Ecommerce propio + Landing Pages + AlexIO Live)

> Este documento reemplaza la sección de arquitectura/fases de `CLAUDE.md` v1. Las reglas de seguridad de la sección 1 de `CLAUDE.md` (tenant_id nunca completado por el modelo, sanitización de IA-Template-Studio) **no cambian y siguen aplicando sin excepción** a todo lo nuevo descrito acá.

**Cambio de visión:** VibeCloud deja de ser "FastAPI + MedusaJS v2 + Next.js" y pasa a ser un **proveedor de hosting multi-tenant** con cuatro productos sobre la misma base de Core:

1. **ERP B2B** — lo que ya existe (`core/`, `routers/`, `services/`, `database/models.py`): ventas, stock/Kardex, clientes, proveedores, caja, picking/WMS. Se mantiene, es la base validada.
2. **Ecommerce propio (B2C)** — reemplaza a MedusaJS. Ya no hay sincronización Core→Medusa; el storefront consume directamente los datos del Core (mismo modelo de `Product`, `Sale`, `BinStock` que ya tiene `tenant_id`).
3. **Landing Pages con IA** — lo que `CLAUDE.md` v1 llamaba "AI Template Studio" (Fase 4). Se mantiene igual, con la misma regla de sanitización obligatoria (1.2).
4. **AlexIO Live** — evolución de AlexIO (Fase 3 de v1): de chat flotante a asistente conversacional en tiempo real, transversal a ERP + ecommerce + landing (no un widget aislado por producto).

---

## 0. Qué se retira

Todo lo acoplado a MedusaJS queda deprecated y se saca del pipeline activo, no se migra:

- `services/medusa_sync.py`, `services/medusa_sync_original.py`
- `routers/api/v1/medusa_sync.py`
- `storefront/` (Next.js actual, hablaba con la API admin de Medusa)
- Servicio `vibecloud-medusa` en `render.yaml` y `digitalocean.yaml`
- El bundle `vibecloud-medusa-20260702-1952.bundle` en la raíz del repo (además de ser un archivo pesado que no debería estar trackeado — ver deuda de seguridad abajo)

Lo que **sí se conserva** de la arquitectura de sincronización, porque ya no hay dos bases de datos separadas que sincronizar:
- El patrón `SyncQueue` con `SELECT FOR UPDATE SKIP LOCKED` (`medusa_sync.py:338`) es reutilizable si en el futuro hay algún proceso async desacoplado (ej. facturación, webhooks salientes), pero deja de ser el mecanismo central del ecommerce.
- El locking pesimista de stock (`with_for_update()` en `stock_service.py`, `bin_stock_service.py`) sigue siendo el corazón de la consistencia entre ERP y ecommerce, porque ahora comparten la misma tabla `BinStock` sin capa intermedia.

**Implicación de arquitectura importante:** al no haber dos DBs separadas (regla que `CLAUDE.md` v1 marcaba como no-negociable en la sección 4, precisamente para no escribir directo a la DB de Medusa), el ecommerce propio puede leer/escribir directo sobre el mismo esquema del Core. Esto simplifica mucho, pero sube el costo de un bug: un endpoint público de ecommerce mal aislado ahora toca la misma base que el ERP. El aislamiento por `tenant_id` (`web/dependencies.py::get_current_tenant`) pasa a ser la única línea de defensa, no hay separación física de por medio como respaldo.

---

## 1. Fases revisadas

### Fase 1 — Fundamentos multi-tenant (ya cumplida, sin cambios)
Ya validado según `CLAUDE.md` v1: `tenant_id` en tablas críticas, `get_current_tenant()`, Kardex, locking de concurrencia. No se reabre.

**Deuda heredada que sí hay que cerrar acá, no después** (ver sección 3): el override de admin por env var en `routers/auth.py` y el rate limit de login que no está wireado.

### Fase 2 — Ecommerce propio reemplaza a Medusa (construido 2026-08-10)
*Objetivo: que un comprador final pueda navegar y comprar sin pasar por Medusa.*

- [x] Catálogo público, detalle de producto (con embed de TikTok), carrito (sesión) y checkout: `routers/storefront.py` + `templates/storefront_*.html`.
- [x] Checkout reutiliza el locking de stock de `stock_service.process_sale` (mismo mecanismo que el POS) vía `services/storefront_order_service.py`.
- [x] Storefront server-rendered desde el mismo FastAPI (Jinja) — sin frontend separado, según lo ya decidido.
- [x] Tenant resuelto exclusivamente por subdominio (`get_public_tenant` en `web/dependencies.py`), nunca por parámetro de request. En producción, un dominio no reconocido da 404, no cae a ningún tenant por defecto.
- [x] **Bug de seguridad encontrado y corregido en el camino:** `routers/store.py` (`/api/v1/store/public-info` y `/public-catalog`, preexistentes) no filtraban por tenant — devolvían el catálogo mezclado de todos los tenants a cualquier visitante. Se corrigió antes de construir el storefront nuevo encima.
- [x] Respeta `TenantCatalog` si el tenant curó su catálogo; si no curó ninguno, muestra todo su catálogo activo por default.
- [ ] Pasarela de pago real — hoy el pedido queda `payment_status="pending"` y lo confirma el vendedor manualmente (efectivo/transferencia) desde el panel. No hay proveedor de pagos online decidido todavía.
- [ ] Object storage (DigitalOcean Spaces) para imágenes — sigue en disco local hasta la migración de infraestructura (Fase de despliegue, sección 6).

**Definition of Done:** ✅ verificado con pruebas automatizadas: compra de punta a punta (catálogo → carrito → checkout → confirmación), stock decrementado correctamente, y aislamiento entre dos tenants confirmado (ninguno ve datos/productos del otro, ni por catálogo ni por acceso directo a un product_id ajeno).

### Fase 3 — Landing Pages con IA (== Fase 4 de v1, sin cambios de fondo)
- [ ] AI Template Studio con sanitización obligatoria (Regla 1.2) desde el primer commit.
- [ ] Landing pages dinámicas vía SSR/ISR.
- Se adelanta en el orden porque ya no depende de que Medusa esté funcionando — antes estaba después de la cascada de IA completa; ahora solo depende del ecommerce propio de Fase 2.

### Fase 4 — AlexIO Live
*De widget de chat a asistente en tiempo real transversal.*

- [ ] Definir el canal real-time: WebSocket propio vs. algo como LiveKit/Pipecat para voz — **no está definido, es la pregunta abierta más grande de todo el documento** (ver sección 4).
- [ ] Reutiliza `AIBrainService` de Fase 2 de v1 (ya con `tenant_id` inyectado server-side, Regla 1.1 aplicada) como cerebro; "Live" es una capa de transporte nueva, no un cerebro nuevo.
- [ ] Si incluye voz: el mismo principio de sanitización de Regla 1.2 aplica a cualquier salida generada que se renderice (subtítulos, transcripciones mostradas en UI).

**Definition of Done:** un usuario interactúa por voz o chat en tiempo real con AlexIO durante una sesión de compra en el ecommerce propio, sin romper el aislamiento de tenant ni exceder cuota de créditos de IA a mitad de conversación.

### Fase 5 — Capa de "hosting provider"
*Esto es lo nuevo que no estaba en v1 en absoluto.*

- [ ] Provisión de dominios custom por tenant (hoy solo hay subdominio vía `BASE_DOMAIN`, ver `_resolve_tenant_from_host` en `web/dependencies.py`) — falta: verificación de dominio, SSL automático (Let's Encrypt / Caddy / el proveedor de hosting que se use).
- [ ] Aislamiento de recursos por tenant a nivel de hosting (no solo `tenant_id` en DB): almacenamiento de assets, límites de uso, posible aislamiento de proceso si un tenant abusa de IA o tráfico.
- [ ] Facturación de hosting como línea de producto separada de los créditos de IA (`ai_tier`/`ai_credits` ya existe para IA; hosting necesita su propio modelo de plan).

**Definition of Done:** un tenant puede conectar un dominio propio y quedar activo con SSL sin intervención manual del equipo.

### Fase 6 — Operación/SuperAdmin (== Fase 5 de v1, sin cambios de fondo)
Dashboard, métricas, health checks — igual que v1, corre en paralelo a partir de que hay tenants reales, no antes.

---

## 2. Qué NO cambia de v1

Las reglas de la sección 5 de `CLAUDE.md` siguen vigentes tal cual:
- No doble partida contable antes de Fase 4-5.
- Capa fiscal agnóstica de país (`FiscalProvider`).
- No sobre-ingeniería de infra antes de tener tenants reales.
- Proceso web y proceso worker separados.

---

## 3. Deuda de seguridad heredada — no se resuelve con el pivot, hay que cerrarla en Fase 1 revisada

Esto viene del review de código hecho sobre el estado actual del repo, sigue pendiente y el pivot de producto no lo toca:

1. **`routers/auth.py:44`** — el override de admin (`ADMIN_EMAIL`/`ADMIN_PASSWORD` por env var) compara password en texto plano con `==`, no `secrets.compare_digest()`, y bypasea el hash de la tabla `User`. Si el ecommerce propio va a exponer más superficie pública, esta puerta trasera de admin es más peligrosa que antes, no menos.
2. **Rate limit de login no wireado** — `RATE_LIMIT_LOGIN=5/minute` existe en `core/config.py` pero no hay `@limiter.limit(...)` en el endpoint `/login`; corre bajo el límite global de 30/minute.
3. **Datos reales expuestos en el repo** (`clientes.xlsx`, `productos.xlsx`, `server_stdout.txt`, `error.log`, `crash.log`, `full_system_export.txt`, el bundle de Medusa) — ver plan de limpieza ya entregado en la conversación. Esto es más urgente ahora, no menos: si se arranca a construir el ecommerce propio sobre este mismo repo, conviene limpiar el historial antes de que el repo tenga más actividad y colaboradores.

---

## 4. Decisiones ya tomadas (2026-08-09)

1. **Storefront:** server-rendered desde el mismo FastAPI, reutilizando `templates/`/Jinja como ya hace el POS. No hay frontend separado. `storefront/` (Next.js) se elimina, no se migra.
2. **Base de datos:** se mantiene una sola base compartida, tenants separados por `tenant_id` (arquitectura ya implementada en Fase 1, sin cambios). No hay bases físicas separadas por cliente.
3. **Medusa:** se saca **por completo** del proyecto, no queda como opción ni como referencia de diseño. Ver sección 0 para el detalle de qué archivos/servicios se eliminan.
4. **AlexIO Live:** solo versión web, chat de texto (sin voz, sin WebRTC/LiveKit), alimentado por Gemini. Reutiliza `AIBrainService` tal cual está — "Live" en este contexto es UX (respuesta rápida/streaming en la misma página), no un canal de transporte nuevo.
5. **Hosting/dominios:** el cliente puede elegir subdominio propio de VibeCloud (gratis, automático) **o** dominio propio conectado. Panel de gestión de dominios vive dentro del `SuperAdmin` (Fase 6), no un panel de hosting genérico tipo cPanel. Capa técnica de HTTPS automático: **Caddy** (open source, certificado solo con indicarle el dominio).
6. **API de venta de dominios:** arrancar con **NameSilo o Dynadot** (sin mínimos de volumen, API simple, buen costo base). Cuando haya volumen real de dominios/mes, sumar **OpenSRS** para esos volúmenes (mejor precio por escala, pero con compromiso mínimo que no tiene sentido asumir todavía).
7. **Landing Pages con IA — refinamiento del flujo:** un chat dentro del panel del cliente donde pega una idea/referencia y se genera una landing con Gemini. Dos reglas de diseño:
   - Pasa por la misma sanitización obligatoria de la Regla 1.2 (allowlist de CSS, validación de schema antes de persistir) — no cambia nada de lo ya definido, solo se le agrega la superficie de chat como input.
   - El prompt de sistema debe orientar a Gemini a generar algo **inspirado** en lo que el cliente pega, no una copia literal de contenido de terceros (riesgo de derechos de autor si el cliente pide clonar un sitio ajeno tal cual).

## 5. Alcance del ecommerce propio (Fase 2) — ya definido

1. **Onboarding masivo de catálogo:** el cliente sube hasta ~3000 imágenes (nombre de archivo = código de producto) + un Excel con los datos adicionales (precio, stock, categoría — mismo tipo de columnas que ya usa `import_productos.py`, que hoy es un script de un solo uso y hay que convertirlo en feature real del panel, multi-tenant, con manejo de imágenes).
   - **"La magia" de la IA acá es emparejamiento automático**: cruzar cada imagen con su producto por el código en el nombre de archivo, para que el cliente no lo haga fila por fila a mano. No genera título/descripción — eso lo define el cliente.
   - Con 3000 imágenes por cliente y potencialmente muchos clientes, esto necesita almacenamiento tipo object storage (S3-compatible — DigitalOcean Spaces, ya que el hosting es en DO), no disco local del servidor.
2. **Videos de TikTok como canal de venta:** cada producto/tienda puede embeber videos de TikTok igual que se embebe un YouTube — pegás el link, se muestra el reproductor. Se implementa con la **API oficial de oEmbed de TikTok** (`developers.tiktok.com/doc/embed-videos/`): le pasás la URL del video público y devuelve el markup del embed oficial. No se descarga ni re-aloja el video en ningún momento — eso sí rompería los términos de TikTok; el embed oficial es el único camino correcto acá.

## 6. Infraestructura (confirmado 2026-08-09)

Google Cloud **queda descartado** como proveedor de infraestructura (Gemini se sigue usando solo como API de IA, eso no cambia). Pila definida:

1. **Compute:** **DigitalOcean App Platform** como proveedor principal (`digitalocean.yaml` ya existe en el repo). `render.yaml` queda como config secundaria/backup — no se mantienen las dos plataformas activas en paralelo a largo plazo, hay que decidir en algún momento si se da de baja una.
2. **Base de datos:** migrar de Supabase a **DigitalOcean Managed PostgreSQL** — esto ya estaba escrito como pendiente en `CLAUDE.md` v1 (sección 5, "Preparación de infraestructura para DigitalOcean") y nunca se ejecutó; hoy la app sigue apuntando a Supabase (`aws-1-us-east-2.pooler.supabase.com`, ver hallazgo de seguridad de la sección 3).
3. **Dominios/SSL de clientes:** **Cloudflare for SaaS** en vez de Caddy — está diseñado específicamente para plataformas donde terceros conectan su propio dominio (emite SSL automático por dominio custom). Reemplaza la propuesta original de Caddy en la sección 4.5.
4. **Redis:** se suma al stack para dos usos concretos:
   - Backend del rate-limiter (`slowapi`, ya en `main.py`) — hoy cuenta en memoria por proceso, lo cual no sirve con más de un worker/instancia corriendo.
   - Cache de catálogo y respuestas de IA, para que el ecommerce sea rápido sin repegarle a la DB o a Gemini por cosas que no cambiaron.

### 6.1 Secuencia de despliegue (confirmado 2026-08-10)

**Etapa 1 — ahora, mientras se hacen los ajustes de las fases 2-5: correr en Render** (`render.yaml`, ya existe en el repo). Es más simple para iterar rápido sin comprometerse todavía a la infraestructura final.
- Base de datos durante esta etapa: se puede seguir usando lo que ya está andando (Supabase) o el Postgres administrado de Render — no vale la pena migrar a DO Managed PostgreSQL todavía si en poco tiempo se muda todo de nuevo. Sí es obligatorio, independientemente de dónde corra, rotar la password de Supabase que quedó expuesta (sección 3) — eso no espera a la migración de infraestructura.
- **No configurar todavía Cloudflare for SaaS ni dominios custom de clientes en esta etapa** — es trabajo de infraestructura que conviene hacer una sola vez, sobre el host final (DigitalOcean), no reconfigurarlo dos veces. Durante Render alcanza con subdominios de prueba.

**Etapa 2 — cuando los ajustes estén cerrados: migrar a DigitalOcean** (`digitalocean.yaml`), siguiendo lo definido en el punto 1-4 de esta sección: App Platform + DO Managed PostgreSQL + Cloudflare for SaaS + Redis. Ahí sí se hace la migración de base de datos y el corte de Supabase.

No se tocan ambos `render.yaml`/`digitalocean.yaml` en paralelo de forma indefinida — Render es la etapa de prueba, DigitalOcean es el destino final.
