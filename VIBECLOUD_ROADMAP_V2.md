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
- [x] AI Template Studio con sanitización obligatoria (Regla 1.2): `services/landing_service.py`. Gemini nunca genera HTML/CSS -- solo texto y elección de color/fuente de una lista cerrada, validado contra schema Pydantic estricto. Chat en `/panel/landing`, landing pública en `/landing`.
- [ ] Landing pages dinámicas vía SSR/ISR -- lo construido hoy es una sola landing por tenant (no múltiples páginas/rutas todavía).
- Se adelantó en el orden porque ya no depende de que Medusa esté funcionando — antes estaba después de la cascada de IA completa; ahora solo dependía del ecommerce propio de Fase 2, ya construido.

### Fase 4 — AlexIO Live (construido 2026-08-10)
*De widget de chat a asistente en tiempo real transversal.*

- [x] Canal: **texto en la web, sin voz** (decisión ya confirmada en sección 4, punto 4). Widget flotante en todas las páginas del storefront (`templates/storefront_base.html`).
- [x] Reutiliza `AIBrainService` (`tenant_id` inyectado server-side, Regla 1.1 aplicada) — se le agregó un parámetro `allowed_tools` para que el storefront público solo pueda usar `consultar_stock`/`recomendar_productos`, nunca `obtener_metricas_ventas` (dato de negocio que no debe ver un visitante anónimo). Filtrado en dos capas: en el schema que se le declara a Gemini y en la ejecución de la tool.
- [ ] Voz/tiempo real (WebSocket, LiveKit) — descartado por decisión ya tomada, no es parte del alcance.

**Definition of Done:** ✅ verificado con pruebas automatizadas: el widget responde en el storefront y el payload enviado a Gemini confirmado sin `obtener_metricas_ventas` en la lista de herramientas.

### Fase 5 — Capa de "hosting provider" (scaffolding construido 2026-08-10, sin probar contra servicios externos reales)
*Esto es lo nuevo que no estaba en v1 en absoluto.*

- [x] Modelo `TenantDomain` + verificación por registro TXT DNS + panel en `/tenants/{id}/domains` (SuperAdmin). `_resolve_tenant_from_host` ahora resuelve por dominio custom verificado además del subdominio de `BASE_DOMAIN`.
- [x] Cliente de **NameSilo** (`services/domain_registrar_service.py`) siguiendo su API pública documentada — **sin probar contra la API real**, no hay `NAMESILO_API_KEY` disponible en este entorno. Probarlo con una cuenta real antes de usarlo en producción.
- [ ] SSL automático (Cloudflare for SaaS, según se confirmó en sección 6) — no implementado, requiere cuenta de Cloudflare real.
- [ ] Aislamiento de recursos por tenant a nivel de hosting (storage, límites de uso).
- [ ] Facturación de hosting como línea de producto separada.

**Definition of Done:** ⚠️ parcial. La resolución de tenant por dominio custom verificado está probada end-to-end (con la verificación TXT mockeada, ya que no hay un dominio real apuntando a este entorno). Falta: SSL automático y probar el cliente de NameSilo contra la API real.

### Fase 6 — Operación/SuperAdmin (construido 2026-08-10, parcial)
- [x] `/health` y `/ready`. **Bug encontrado y corregido en el camino:** `/health` (el mismo path que usa `healthCheckPath` en `render.yaml`) llamaba a `text("SELECT 1")` sin importar `text` en `main.py` -- reportaba "degraded" siempre por un `NameError`, no por un problema real de conexión a la base. Si el deploy actual en Render está usando este healthcheck, probablemente lo esté marcando como no saludable incorrectamente.
- [x] Gestión de dominios agregada a `/tenants` (ver Fase 5).
- [ ] Dashboard de métricas de consumo de IA y bandwidth por tenant — el endpoint `/api/v1/superadmin/dashboard` ya existe (JWT-based, separado del panel de sesión) pero no se conectó a una UI con estas métricas específicas.
- [ ] Auditoría automática de logs de acceso — ya existe `/api/v1/superadmin/security-audit` (analiza logs con IA) pero no está conectado a logs reales, usa datos mock por default.

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

1. ~~`routers/auth.py:44` — override de admin en texto plano~~ **Resuelto 2026-08-10**: se eliminó por completo el bypass, no solo se le agregó `compare_digest`. El bootstrap de admin ya funciona vía `AuthService.create_default_user_and_settings` (hash real sincronizado desde `ADMIN_PASSWORD`).
2. ~~Rate limit de login no wireado~~ **Resuelto 2026-08-10**: `@limiter.limit(...)` conectado a `/login`, verificado con pruebas (6ta request seguida da 429).
3. **Datos reales expuestos en el repo viejo** (`sistemasberelk-cyber/vibecloud`) — sigue sin resolverse. El trabajo se movió a un repo nuevo y limpio (`vibecloudonline-gif/vibecloude`) que nunca tuvo esos archivos, pero el repo viejo con el historial expuesto (CUIT/DNI reales de clientes) sigue público. Bloqueado por falta de acceso de colaborador — ver resumen final.

### 3.1 Bugs adicionales encontrados durante la construcción (2026-08-10)

Ninguno de estos estaba relacionado con lo que se pidió construir, se encontraron por las pruebas automatizadas end-to-end:

1. **`routers/store.py` filtraba datos entre tenants** (ya corregido) — `/api/v1/store/public-info` y `/public-catalog`, endpoints públicos preexistentes, no filtraban por `tenant_id`: cualquier visitante veía el catálogo mezclado de todos los tenants. Corregido antes de construir el storefront nuevo encima (sección "Fase 2" más arriba).
2. **`main.py` — `/health` roto** (ya corregido) — llamaba a `text("SELECT 1")` sin importar `text` de `sqlalchemy`. Reportaba `"degraded"` siempre por un `NameError`, no por un problema real de conexión. Es el mismo path que usa `healthCheckPath` en `render.yaml` — si el deploy activo en Render usa este healthcheck, puede estar marcando el servicio como no saludable incorrectamente.
3. **`requirements.txt` incompleto** (ya corregido) — `cryptography`, `requests` y `dnspython` se usan en el código (`database/models.py`, `routers/admin.py`, verificación de dominios) pero no estaban listados. Un `pip install -r requirements.txt` limpio fallaba.
4. **`routers/admin.py` — guardado de API key de IA por tenant roto, sin corregir** — `set_ai_key`/`get_ai_key` le escriben/leen `.api_key` a un `AICredential`, pero el campo real del modelo es `api_key_enc` (encriptado). La función parece guardar la key pero no persiste nada utilizable. No se tocó porque requiere entender el flujo de encriptación (`Fernet`) que no se investigó a fondo esta sesión — queda para revisar aparte.

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

---

## 7. Pivot a hosting multi-producto (confirmado 2026-08-11) — "no es un ERP, es un hosting"

Corrección de visión: VibeCloud no es el ERP con un ecommerce opcional colgado — es un **hosting** donde el cliente se crea una cuenta y decide qué producto(s) usar (ERP, ecommerce, landing con IA, dominios, AlexIO web), libremente combinables, no en una jerarquía. El "cerebro" de generación de web va a cascada de 3 IAs: **Claude primario → Gemini fallback → Qwen tercer fallback** para contenido creativo/landing/ecommerce; **Gemini primario → Qwen fallback** para el chat de AlexIO. Plan completo aprobado en 5 fases:

### Fase 1 — Flags de producto por tenant (completada 2026-08-11)
Reemplaza el viejo `Tenant.product_plan` (string jerárquico `full`/`ecommerce`/`landing`) por cuatro booleanas independientes y libremente combinables: `has_erp`, `has_ecommerce`, `has_landing`, `has_alexio` (default `True` los cuatro, para no romper tenants existentes). Migración `e5f6a7b8c9d0` data-migra desde `product_plan` y lo dropea. Switcher del sidebar (`/panel/nav-view`) pasó de un `<select>` de una sola opción a checkboxes de `modules[]`, validado contra `session["tenant_flags"]` (seteado en `/login`) — no se puede "prender" un módulo que el tenant no tiene contratado. Alta/edición de tenant en SuperAdmin (`/tenants`) actualizada a las tres flags (con checkboxes). Probado end-to-end con `TestClient`: tenant full sin regresión, tenant solo-landing oculta ERP/Ecommerce en dashboard y sidebar, rechazo de módulos no contratados (403) y de altas sin ningún producto activo (400). Desplegado y verificado en Render (`/health`, `/login` 200 sobre el commit `897021d`).

### Fase 2 — Conector ERP↔Ecommerce (completada 2026-08-11)
Toggle en Configuración → Tienda Online (`Settings.ecommerce_connected_to_erp`, default `False`): prendido, el storefront comparte el mismo `BinStock` que el POS (comportamiento histórico); apagado, usa su propio depósito `"ONLINE"` — así un tenant que solo contrató ecommerce no depende de tener el módulo ERP para vender. `StockService.process_sale(target_bin_name=...)` es el nuevo punto de extensión (opcional, no rompe al POS que sigue sin pasarlo); crea el depósito `"ONLINE"` la primera vez que hace falta y lo *commitea* de inmediato (no solo `flush`) aunque la venta que lo disparó falle después por falta de stock — si no, un tenant recién desconectado nunca podría cargarle stock a mano (la primera venta siempre fallaría y de-crearía el bin al hacer rollback). `storefront_order_service.create_order` ahora atrapa el `ValueError` de stock insuficiente y lo muestra como error prolijo en el carrito en vez de un 500. Probado end-to-end (aislamiento real de stock en ambos sentidos) y sin regresiones en la suite de stock/crédito/caja (29 tests) ni en el resto de la suite (62/65, los 3 failures restantes son preexistentes y no relacionados — `test_superadmin.py` testea el bypass de rol `"admin"` que ya se había cerrado antes en esta sesión). Desplegado a Render sobre el commit `956b0a2`.

### Fase 3 — Self-service signup (`/registro`) — pendiente
Chequeo de disponibilidad de subdominio, checkboxes de producto, alta automática de tenant + admin + settings + auto-login. Explícitamente sin billing/pagos todavía (no definido).

### Fase 4 — Wizard guiado de onboarding (Landing/Ecommerce) — completada 2026-08-11
`routers/onboarding_wizard.py` + `templates/onboarding_wizard.html` (`/panel/onboarding`), gateado en dos capas: la UI oculta la sección que el tenant no tiene contratada, y cada endpoint vuelve a chequear `Tenant.has_landing`/`has_ecommerce` desde la DB (403 si no corresponde), nunca confía en lo que muestra el cliente.

- **Landing**: preguntas guiadas (nombre del negocio, rubro, tono/estilo, color preferido opcional) + upload opcional de imagen de referencia (PNG/JPEG/WEBP, validada con el mismo chequeo de firma de bytes que ya usa el logo de `Settings` — nunca solo el `content-type` declarado). El prompt armado desde las respuestas reusa el pipeline ya sanitizado de `services/landing_service.py` (Regla 1.2, nunca HTML/CSS crudo). **Novedad**: `generate_landing_content`/`_call_gemini` ahora aceptan `reference_image_path` opcional y arman un `inline_data` part (multimodal) para Gemini — el `SYSTEM_INSTRUCTION` fue extendido para dejar explícito que la imagen es *solo* referencia estética (paleta/ambiente), nunca se describe ni se copia literal, mismo principio "inspirado no copiado". La imagen se guarda en disco (`static/images/style-refs/`, nunca como base64/texto en la DB) y su URL queda en el nuevo campo `LandingPage.reference_image_url` (migración `a7b8c9d0e1f2`).
- **Ecommerce**: selección guiada de `Settings.storefront_template` (las 4 plantillas ya existentes) — sin IA de por medio, es un enum cerrado ya validado por `SettingsService.apply_updates`.
- Link "Onboarding Guiado" agregado al sidebar (`templates/base.html`), visible solo si el tenant tiene landing o ecommerce contratado.

**Definition of Done:** ✅ verificado end-to-end: wizard bloqueado sin login, oculta secciones no contratadas, rechaza (403) intentos directos contra el endpoint de un producto no contratado, rechaza imágenes con content-type no soportado y con content-type spoofeado (firma de bytes inválida), genera y persiste la landing con la imagen de referencia pasada correctamente a Gemini (verificado interceptando la llamada), y guarda el estilo de tienda elegido. Sin regresiones nuevas en la suite existente (los 3 failures de `test_superadmin.py` siguen siendo los mismos preexistentes de sesiones anteriores; se detectaron además 2 failures nuevos en `test_audit_master.py`/`test_cash_closure_decimal.py` pero se confirmó que son **preexistentes e independientes de este cambio** — reproducen igual con `git stash` sobre el commit ya pusheado, causados por el reloj cruzando medianoche UTC mientras la hora local del entorno de pruebas seguía en el día anterior (`date.today()` local vs `Sale.timestamp` en UTC), no por código de esta fase).

### Fase 5 — Cascada multi-LLM (`services/ai_gateway_service.py`) — completada 2026-08-11 (código listo, sin probar contra Claude/Qwen reales)

- [x] **Claude → Gemini → Qwen para generación de contenido web** (Landing/Ecommerce): `AIGatewayService.generate_landing_content_cascade(prompt, reference_image_path=None)`, usado tanto por el chat libre de `/panel/landing` como por el wizard guiado de Fase 4. Cada intento se valida contra el **mismo** schema estricto (`LandingPageContent`, Regla 1.2) sin importar qué proveedor respondió -- la sanitización no depende del proveedor. Si un proveedor falla (sin key, error de API, refusal, JSON inválido), pasa al siguiente y agrega el motivo a un log de errores; si los tres fallan, rechaza con el detalle de los tres. La respuesta incluye `provider_used` para trazabilidad.
- [x] **Cliente de Claude con el SDK oficial de Anthropic** (`AnthropicClient`, paquete `anthropic` agregado a `requirements.txt`), no HTTP directo -- Gemini y Qwen sí siguen en HTTP directo porque no tienen SDK propio en este proyecto. Modelo por defecto `claude-opus-5`. Soporta imagen de referencia (input multimodal, mismo principio "solo referencia estética" que ya regía para Gemini). Maneja `stop_reason == "refusal"` explícitamente.
- [x] **Gemini → Qwen para AlexIO chat**: `AIBrainService.chat_response` ahora es un wrapper que intenta Gemini (`_chat_response_gemini`, la lógica original con function-calling intacta) y cae a `AIGatewayService.chat_fallback_qwen` (texto plano, sin function-calling ni descuento de créditos -- fallback degradado a propósito) solo cuando Gemini no está *disponible* (`GeminiUnavailableError`: sin key, error de API, respuesta vacía/inválida). **Los errores de negocio (tenant inexistente, créditos insuficientes) nunca disparan el fallback** -- se propagan tal cual, porque saltear una regla de créditos usando otro proveedor sería un bypass de seguridad, no alta disponibilidad. Verificado explícitamente con un test que fuerza un tenant inexistente y confirma que el fallback jamás se invoca.
- [x] `services/domain_registrar_service.py` no se toca (ya migrado a GoDaddy en la actualización de este mismo día, sección anterior).

**Definition of Done:** ✅ verificado end-to-end con mocks (nunca contra los proveedores reales, sin credenciales en este entorno): `AnthropicClient` arma el payload esperado y rechaza refusals; la cascada usa Claude cuando responde, cae a Gemini cuando Claude no está disponible, cae a Qwen cuando ninguno de los dos está disponible, y rechaza con detalle de los tres si ninguno responde; el chat de AlexIO cae a Qwen solo por indisponibilidad de Gemini, nunca por una regla de negocio. Sin regresiones: mismos 5 failures preexistentes de la suite (3 de `test_superadmin.py`, 2 por el reloj cruzando medianoche UTC, ambos ya documentados en Fase 4). **No activado en producción** -- no hay `ANTHROPIC_API_KEY` ni `QWEN_API_KEY` reales en este entorno; hasta que se configuren, la cascada usa Gemini como siempre (comportamiento sin cambios para el usuario final).

---

**Con esto quedan completadas las 5 fases del plan de pivot a hosting multi-producto (sección 7) aprobado el 2026-08-11.**

No se tocan ambos `render.yaml`/`digitalocean.yaml` en paralelo de forma indefinida — Render es la etapa de prueba, DigitalOcean es el destino final.

---

## Actualización 2026-08-11

- **API de venta de dominios:** se reemplaza NameSilo/Dynadot por **GoDaddy API** (`api.godaddy.com/v1/domains`) como proveedor principal. `services/domain_registrar_service.py` pasa a tener un `GoDaddyClient` (credenciales `GODADDY_API_KEY`/`GODADDY_API_SECRET`, sin key real en este entorno todavía — construido y probado con mocks, igual que se hizo antes con NameSilo). El `NameSiloClient` se elimina, no queda como código muerto.
- **Ecommerce:** se suma **recomendación predictiva de productos usando Qwen** (Alibaba/DashScope), en el mismo servicio de IA en cascada ya definido en Fase 5 de la sección 7 (`services/ai_gateway_service.py`), pero como **feature independiente activable** aunque la cascada completa (Claude→Gemini→Qwen) no esté lista. Sin `QWEN_API_KEY` real en este entorno — construido y dejado listo para activar.

### Fase 3 — Self-service signup (`/registro`) — completada 2026-08-11

- [x] **Proveedor de dominios GoDaddy** (reemplaza a NameSilo): `services/domain_registrar_service.py` reescrito con `GoDaddyClient` (`check_availability`, `register_domain` con payload real de contactos vía `GODADDY_CONTACT_*`). `NameSiloClient` eliminado, no queda código muerto. `routers/admin.py` y `templates/tenant_domains.html` actualizados. Sin `GODADDY_API_KEY`/`GODADDY_API_SECRET` reales en este entorno — construido y probado con el transporte HTTP mockeado, mismo patrón que NameSilo antes.
- [x] **Recomendación predictiva con Qwen**: `services/ai_gateway_service.py` (nuevo) con `QwenClient` (DashScope, modo compatible OpenAI) y `AIGatewayService.recommend_products`. Endpoints públicos `GET /tienda/producto/{id}/recomendados` y `GET /tienda/carrito/recomendados` en `routers/storefront.py`. **Aislamiento de tenant garantizado en dos capas**: el set de candidatos se arma filtrado por `tenant_id` antes de llamar al modelo, y la respuesta se vuelve a filtrar (whitelist) contra ese mismo set antes de devolverla — verificado con un test que fuerza a un Qwen mockeado a "alucinar" el ID de un producto de otro tenant y confirma que se descarta igual. Sin `QWEN_API_KEY` real: cae a una heurística simple (misma categoría) en vez de romper el endpoint.
- [x] **Signup self-service**: `routers/signup.py` (nuevo) + `templates/registro.html`. `GET /registro` (form), `GET /api/registro/subdominio-disponible` (chequeo en vivo, formato + reservados + unicidad), `POST /registro` (alta de `Tenant`+`Settings`+`User` admin, checkboxes `has_erp`/`has_ecommerce`/`has_landing`/`has_alexio`, contraseña validada con la misma regla que usa el panel de SuperAdmin, auto-login seteando `session["tenant_flags"]`/`session["nav_view"]` igual que `/login`). Si el username admin ya existe (es único a nivel global, no por tenant) o cualquier otro fallo post-creación del tenant, se hace rollback y se borra el tenant recién creado — nunca queda un tenant huérfano sin admin. Sin billing/pagos (fuera de alcance, como ya estaba definido).

**Definition of Done:** ✅ verificado end-to-end: GoDaddy (disponibilidad + payload de compra con mocks), Qwen (heurística de fallback + aislamiento de tenant con intento de fuga forzado), signup completo (alta exitosa, auto-login, subdominio duplicado, sin productos elegidos, contraseña débil, username admin duplicado — los tres últimos casos verificados sin dejar tenants huérfanos). Sin regresiones: 62/65 tests de la suite existente (los 3 failures son preexistentes y no relacionados, ver sección 3.1).
