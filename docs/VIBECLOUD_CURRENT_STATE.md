# VIBECLOUD — AUDITORÍA DE ESTADO ACTUAL DEL REPOSITORIO

> Generado: 2026-08-23
> Método: inspección archivo por archivo del código real, no de documentación ni comentarios.
> Clasificación: IMPLEMENTADO | PARCIAL | MOCK | STUB | NO IMPLEMENTADO | ROTO

---

## TABLA MAESTRA

| # | Módulo | Estado | Archivos clave (líneas) | Problema | Acción recomendada |
|---|--------|--------|------------------------|----------|-------------------|
| **AI SERVICES** | | | | | |
| 1 | AIBrainService (AlexIO chat) | **IMPLEMENTADO** | `services/ai_brain_service.py` (332) | 3 integraciones Gemini paralelas sin unificar | Candidato principal para el Cognitive Router |
| 2 | AIGatewayService (cascada) | **IMPLEMENTADO** (sin probar vs APIs reales) | `services/ai_gateway_service.py` (530) | Sin `ANTHROPIC_API_KEY` ni `QWEN_API_KEY` reales | Activar con credenciales, no reescribir |
| 3 | GeminiService (legacy) | **IMPLEMENTADO** | `services/gemini_service.py` (325) | Duplica funcionalidad de AIBrainService con distinto modelo | Migrar a Gateway unificado |
| 4 | LandingService | **IMPLEMENTADO** | `services/landing_service.py` (232) | Funciona bien, validación Pydantic estricta | Mantener, enrutar vía Gateway |
| 5 | Router AI | **IMPLEMENTADO** (1 mock) | `routers/ai.py` (419) | `/image` es MOCK (placeholder). `/credits/buy` suma créditos gratis sin pago | Cerrar `/credits/buy`, implementar imagen |
| 6 | LLM stubs (DeepSeek, OpenAI) | **STUB (muerto)** | `services/llm/*.py` (56 total) | Nunca importados, deps no en requirements | **ELIMINAR** |
| 7 | Voice stubs (ElevenLabs, Google) | **STUB (muerto)** | `services/voice/*.py` (105 total) | Nunca importados, deps no en requirements | **ELIMINAR** |
| 8 | WhatsApp service | **STUB (ROTO)** | `services/whatsapp_service.py` (33) | Imports relativos rotos, sin webhook receiver | **ELIMINAR** |
| 9 | Provider factory | **STUB (ROTO)** | `services/provider_factory.py` (25) | Imports relativos rotos, solo usado por whatsapp | **ELIMINAR** |
| **ERP** | | | | | |
| 10 | Productos / Catálogo | **IMPLEMENTADO** | `routers/products.py` (331), `services/catalog_import_service.py` (213) | Categorías como string, no entidad separada | Bajo riesgo, mejora futura |
| 11 | Ventas / POS | **IMPLEMENTADO** | `routers/sales.py` (241), `services/stock_service.py` (323) | Código muerto después de `return sale` (líneas 291-296) | Limpiar dead code |
| 12 | Stock / WMS / Kardex | **IMPLEMENTADO** | `routers/wms.py` (613), `services/bin_stock_service.py` (342) | Ninguno | Sólido, no tocar |
| 13 | Clientes | **IMPLEMENTADO** | `routers/clients.py` (270) | Sin búsqueda/filtros avanzados, sin tags | Mejora futura |
| 14 | Proveedores / Compras | **IMPLEMENTADO** | `routers/suppliers.py` (112), `services/purchase_service.py` (221) | Ninguno | Sólido |
| 15 | Caja / Tesorería | **IMPLEMENTADO** | `routers/cash.py` (116), `services/cash_service.py` (116) | Ninguno | Sólido |
| 16 | Cuentas por cobrar | **IMPLEMENTADO** | Lógica distribuida en stock_service, clients, sales | Ninguno | Sólido |
| 17 | Reportes | **PARCIAL** | `routers/reports.py` (63) | **BUG: `timezone` y `timedelta` no importados** — `/reports/cash-flow` crashea con NameError | **FIX URGENTE** |
| **STOREFRONT** | | | | | |
| 18 | Router storefront | **IMPLEMENTADO** | `routers/storefront.py` (340) | Ninguno | Funcional |
| 19 | Renderer data-driven | **IMPLEMENTADO** | `services/storefront_renderer.py` (382) | Sin UI para editar `site_config_json` | Fase siguiente |
| 20 | 4 temas (elegante/urbano/natural/tech) | **IMPLEMENTADO** | En storefront_renderer.py | Cada tema genera CSS variables distintas reales | Verificar visualmente |
| 21 | Block templates (7) | **IMPLEMENTADO** (5), **STUB** (1), **MOCK** (1) | `templates/blocks/*.html` | `category_grid`: sin data source. `newsletter`: form no hace nada | Conectar o documentar como futuro |
| 22 | storefront_catalog.html (legacy) | **ROTO** | `templates/storefront_catalog.html` (25) | Usa clases CSS no definidas, no lo renderiza ningún endpoint | **ELIMINAR** |
| 23 | Storefront order service | **IMPLEMENTADO** | `services/storefront_order_service.py` (149) | Pedidos quedan en `payment_status="pending"` | Conectar con pasarela de pago |
| **LANDING PAGES** | | | | | |
| 24 | Landing generation | **IMPLEMENTADO** | `services/landing_service.py` (232) | Funciona con Gemini, cascada a Claude/Qwen vía gateway | Enrutar vía Gateway centralizado |
| 25 | Landing studio (admin) | **IMPLEMENTADO** | `routers/landing_studio.py`, `templates/landing_studio.html` (97) | Una sola landing por tenant | Múltiples landings = mejora futura |
| 26 | Landing pública | **IMPLEMENTADO** | `templates/storefront_landing.html` (59) | Funciona | - |
| **AUTH & MULTI-TENANT** | | | | | |
| 27 | Auth (sesiones) | **IMPLEMENTADO** | `routers/auth.py` (79), `services/auth_service.py` (102) | Sesión cookie sin `max_age`, sin revocación server-side | Bajo riesgo por ahora |
| 28 | Auth (JWT) | **IMPLEMENTADO** | `routers/api/v1/auth.py` (144), `services/jwt_service.py` (36) | Refresh token rotation funcional | Sólido |
| 29 | Aislamiento multi-tenant | **IMPLEMENTADO** | `web/dependencies.py` (254) | Dev mode fallback a tenant 1 si no hay auth/host | Riesgo si ENVIRONMENT mal configurado |
| 30 | Roles/permisos | **IMPLEMENTADO** | Distribuido en dependencies + services | Sin middleware, sin tabla ACL, roles son strings | Suficiente por ahora |
| 31 | Signup self-service | **IMPLEMENTADO** | `routers/signup.py` (321) | Sin CAPTCHA, solo rate limit | CAPTCHA = mejora futura |
| 32 | Equipo (team) | **IMPLEMENTADO** | `routers/team.py` (134) | Funcional | - |
| 33 | Email confirmation | **IMPLEMENTADO** (opt-in) | `services/email_service.py` (81) | Requiere SMTP_HOST, sin él crea cuentas activas directo | Por diseño |
| 34 | SuperAdmin API | **PARCIAL** | `routers/superadmin.py` (143) | `/security-audit` usa datos mock hardcodeados | Conectar a logs reales |
| 35 | SuperAdmin Web | **IMPLEMENTADO** | `routers/admin.py` (1108) | Funcional | - |
| 36 | Rate limiting | **IMPLEMENTADO** (in-memory) | `core/limiter.py` (18) | **No funciona con múltiples workers** | Migrar a Redis |
| **PAYMENTS** | | | | | |
| 37 | PayPal provider | **IMPLEMENTADO** (dormant) | `services/payment_service.py` (292) | Sin credenciales en ningún entorno | Activar con keys |
| 38 | Stripe provider | **IMPLEMENTADO** (dormant) | `services/payment_service.py` (292) | Webhook verify real (HMAC), sin credenciales | Activar con keys |
| 39 | Payment router (3 flujos) | **IMPLEMENTADO** | `routers/payments.py` (372) | PayPal webhook verify incompleto (no verifica firma) | Completar verificación |
| **DOMAINS** | | | | | |
| 40 | Panel dominios (self-service) | **IMPLEMENTADO** | `routers/panel_domains.py` (110) | Solo solicita, nunca compra automáticamente | Por diseño |
| 41 | Panel dominios (SuperAdmin) | **IMPLEMENTADO** | `routers/admin.py` (líneas 604-764) | CRUD + compra + verificación TXT | Funcional |
| 42 | GoDaddy client | **PARCIAL** | `services/domain_registrar_service.py` (138) | Código completo, nunca probado contra API real | Probar con sandbox |
| **INFRAESTRUCTURA** | | | | | |
| 43 | Main app | **IMPLEMENTADO** | `main.py` (215) | Exception handler expone stack traces en producción | **FIX: no retornar traceback al cliente** |
| 44 | Config | **IMPLEMENTADO** | `core/config.py` (48) | Sin variables Medusa muertas (ya limpio) | - |
| 45 | Database session | **IMPLEMENTADO** | `database/session.py` (74) | `supabase_client` creado pero nunca usado | Limpiar |
| 46 | Alembic (19 migraciones) | **IMPLEMENTADO** | `alembic/versions/` (19 archivos) | Auto-upgrade en startup, fallback a create_all | Funcional |
| 47 | Deploy configs | **IMPLEMENTADO** | `render.yaml`, `digitalocean.yaml`, `Dockerfile`, `docker-compose.yaml` | `digitalocean.yaml` tiene SECRET_KEY hardcodeado | **FIX** |
| 48 | Redis | **NO IMPLEMENTADO** | Solo en deploy configs | Provisionado en render/DO/docker pero 0 líneas de Python lo usan. `redis` no está en requirements.txt | Implementar cuando sea necesario |
| 49 | CI/CD | **NO IMPLEMENTADO** | Ninguno | Sin GitHub Actions, sin pipeline | Crear |
| 50 | Workers | **NO IMPLEMENTADO** | `workers/__init__.py` (0 líneas) | Archivo vacío | Futuro |
| 51 | Logging | **IMPLEMENTADO** | `core/logging_config.py` (21) | JSON estructurado, file + stream. `crash.log` tiene error real | Funcional |
| 52 | Tests | **PARCIAL** | `tests/` (23 archivos, 121 tests, 4350 líneas) | ~106/110 pasan. 3 failures preexistentes (test_superadmin), 2 intermitentes (reloj) | Agregar CI |
| **CÓDIGO MUERTO** | | | | | |
| 53 | `services/llm/*.py` | **STUB (muerto)** | 3 archivos (56 líneas) | DeepSeek + OpenAI, deps no instaladas | **ELIMINAR** |
| 54 | `services/voice/*.py` | **STUB (muerto)** | 3 archivos (105 líneas) | ElevenLabs + Google, deps no instaladas | **ELIMINAR** |
| 55 | `services/whatsapp_service.py` | **STUB (ROTO)** | 1 archivo (33 líneas) | Imports rotos, sin webhook | **ELIMINAR** |
| 56 | `services/provider_factory.py` | **STUB (ROTO)** | 1 archivo (25 líneas) | Imports rotos, solo usado por whatsapp | **ELIMINAR** |
| 57 | `frontend/` | **NO IMPLEMENTADO** | ~40 archivos | Next.js 16 abandonado, sin node_modules, themes distintos a backend | **ELIMINAR o archivar** |
| 58 | `storefront_catalog.html` | **ROTO** | 1 archivo (25 líneas) | CSS clases no definidas, no renderizado | **ELIMINAR** |
| 59 | Medusa residuos | **PARCIAL (inerte)** | `Product.medusa_product_id`, `ProcessedWebhook.source="medusa"` | Campos en modelos, scripts sueltos | Limpiar en pase dedicado |
| 60 | `routers/api/v1/inventory.py` | **ROTO** | Línea 33: `tenant_id = 1` hardcodeado | Legacy Medusa webhook, rompe multi-tenancy | **FIX o ELIMINAR** |

---

## MODELOS DE BASE DE DATOS (31 tablas)

| Modelo | tenant_id | Campos | Nota |
|--------|-----------|--------|------|
| Tenant | N/A (es el tenant) | 10 | Flags: has_erp, has_ecommerce, has_landing, has_alexio |
| TenantDomain | ✅ | 7 | Unique domain constraint |
| SupportTicket | ✅ | 8 | Composite index tenant+status |
| Settings | ✅ | 12 | Incluye site_config_json (nuevo) |
| **Tax** | **❌** | 4 | **Global — un tenant cambia la tasa y afecta a todos** |
| Client | ✅ | 15 | Soft delete |
| User | ✅ | 11 | Unique (tenant_id, username) |
| TenantCatalog | ✅ | 3 | Bridge table |
| LandingPage | ✅ | 6 | Unique per tenant |
| Product | ✅ | 17 | Aún tiene `medusa_product_id` (inerte) |
| SyncQueue | ✅ | 10 | Legacy Medusa |
| **ProcessedWebhook** | **❌** | 4 | Legacy, event_id PK |
| Sale | ✅ | 9 | Composite index tenant+timestamp |
| SaleItem | ❌ (vía Sale FK) | 7 | Aislado indirectamente |
| PaymentAllocation | ❌ (vía Sale FK) | 4 | Aislado indirectamente |
| AccountReceivable | ✅ | 9 | |
| Payment | ✅ | 7 | |
| Supplier | ✅ | 8 | Soft delete |
| Purchase | ✅ | 7 | Soft delete |
| PurchaseItem | ❌ (vía Purchase FK) | 6 | Aislado indirectamente |
| CashMovement | ✅ | 9 | |
| Location | ✅ | 8 | Unique (tenant, code) |
| Bin | ✅ | 10 | Unique (tenant, location, name) |
| BinStock | ✅ | 5 | CHECK qty >= 0 |
| StockMovement | ✅ | 10 | |
| **BusinessConfig** | **❌** | 7 | **Legacy, config global de IA — no per-tenant** |
| AICredential | ✅ | 4 | Encrypted (Fernet) |
| RefreshToken | ✅ | 7 | |
| PlatformPayment | ✅ | 12 | |
| UIConfig | ✅ | 5 | |

---

## INVENTARIO DE MODELOS DE IA (referencias hardcodeadas)

| Ubicación | Modelo | Proveedor |
|-----------|--------|-----------|
| `ai_brain_service.py:171` | gemini-3.1-flash-lite, gemini-3.5-flash, gemini-3.1-pro | Google Gemini |
| `ai_gateway_service.py:51` | claude-opus-5 | Anthropic |
| `ai_gateway_service.py:59` | qwen-plus | Alibaba DashScope |
| `gemini_service.py:14` | gemini-2.0-flash | Google Gemini |
| `gemini_service.py:260,308` | gemini-2.5-flash | Google Gemini |
| `landing_service.py:34` | gemini-3.5-flash | Google Gemini |
| `routers/ai.py:52,85` | gemini-2.5-flash | Google Gemini (inline URL) |
| `routers/admin.py:500` | gemini-3.5-flash | Google Gemini (inline URL) |
| `routers/ai.py:347` | gemini-3.1-pro | Google Gemini |
| `routers/superadmin.py:136` | gemini-3.1-pro | Google Gemini |
| `llm/deepseek_provider.py:14` | deepseek-chat | DeepSeek (**muerto**) |
| `llm/openai_provider.py:10` | gpt-4-turbo-preview | OpenAI (**muerto**) |

**Hallazgo:** Al menos 4 versiones distintas de Gemini se usan en paralelo sin una abstracción unificadora. Cada servicio elige su modelo directamente.

---

## BUGS ENCONTRADOS EN LA AUDITORÍA

| # | Severidad | Ubicación | Bug | Impacto |
|---|-----------|-----------|-----|---------|
| 1 | **ALTA** | `routers/reports.py:46` | `timezone` y `timedelta` no importados | `/reports/cash-flow` crashea con NameError |
| 2 | **ALTA** | `main.py:210-215` | Exception handler retorna traceback completo al cliente | Expone internos en producción |
| 3 | **ALTA** | `routers/api/v1/inventory.py:33` | `tenant_id = 1` hardcodeado | Rompe multi-tenancy para webhooks |
| 4 | **ALTA** | `routers/ai.py:401-419` | `/credits/buy` sin role check y sin payment gate | Cualquier usuario autenticado suma créditos gratis |
| 5 | **MEDIA** | `digitalocean.yaml` | `SECRET_KEY: default-secret-key-change-in-prod` hardcodeado | Riesgo si se despliega sin cambiar |
| 6 | **MEDIA** | `Tax` modelo | Sin `tenant_id` | Tasas de impuesto compartidas globalmente |
| 7 | **MEDIA** | `services/payment_service.py` (PayPal) | Webhook verify solo parsea JSON, no verifica firma | Payloads falsos serían aceptados |
| 8 | **BAJA** | `services/stock_service.py:291-296` | Código muerto después de `return sale` | Inofensivo, cleanup pendiente |
| 9 | **BAJA** | `database/session.py` | `supabase_client` creado pero nunca usado | Objeto muerto en namespace |
| 10 | **BAJA** | `crash.log` | Contiene error real: `Sale.total` (ya corregido a `total_amount`) | Archivo de log viejo, no afecta runtime |

---

## OBSERVACIONES ARQUITECTÓNICAS CLAVE

### 1. Tres caminos paralelos a Gemini sin unificar
- `AIBrainService` — AlexIO con function calling (gemini-3.5-flash / 3.1-pro)
- `GeminiService` — utilidad legacy para UI/copy/chat (gemini-2.0-flash / 2.5-flash)
- Llamadas inline en `routers/ai.py` — httpx directo (gemini-2.5-flash)

Cada uno elige modelo y formato distinto. No hay abstracción común. El Gateway (ai_gateway_service.py) unifica Claude/Gemini/Qwen para la cascada de landings, pero AIBrainService y GeminiService no pasan por él.

### 2. 219 líneas de código muerto identificadas
- `services/llm/` (56 líneas) — DeepSeek + OpenAI stubs
- `services/voice/` (105 líneas) — ElevenLabs + Google stubs
- `services/whatsapp_service.py` (33 líneas) — imports rotos
- `services/provider_factory.py` (25 líneas) — imports rotos

Todo este código pertenece a un pipeline de WhatsApp con voz que nunca se construyó. Ningún router lo importa.

### 3. Redis provisionado pero nunca conectado
Está en `render.yaml`, `digitalocean.yaml` y `docker-compose.yaml`. El paquete `redis` de Python NO está en `requirements.txt`. Cero líneas de código lo usan. El rate limiter usa `MemoryStore` (una instancia por worker, inefectivo con múltiples workers).

### 4. Sin CI/CD
No hay GitHub Actions ni ningún pipeline. Los tests (121 funciones, ~106 pasan) solo se corren manualmente. Deploy es git push a Render.

### 5. Aislamiento multi-tenant sólido pero no perfecto
- `Tax` y `BusinessConfig` son globales (sin tenant_id)
- `inventory.py` tiene `tenant_id = 1` hardcodeado
- Dev mode cae a tenant 1 sin autenticación
- No hay middleware de enforcement — cada router debe usar el dependency correcto

### 6. Storefront data-driven ya existe
El renderer (`services/storefront_renderer.py`) con SiteConfig + ThemeTokens + Block Registry + 4 temas visualmente distintos ya está construido y wired al router. Lo que falta: UI para editar `site_config_json`, y que la IA genere secciones validadas contra este schema.

---

## RESUMEN POR ÁREA PARA EL PLAN DE 28 FASES

| Fase del plan | ¿Qué existe ya? | ¿Qué falta? |
|---------------|-----------------|--------------|
| F0 Auditoría | Este documento | — |
| F1 AI Gateway | `ai_gateway_service.py` (parcial — solo landing cascade + Qwen recs) | Unificar las 3 rutas a Gemini bajo un solo gateway |
| F2 AI Request Contract | No existe | Crear schema unificado |
| F3 Provider Registry | No existe (solo `PROVIDERS` dict en payment_service) | Crear para IA |
| F4 Model Registry | Modelos hardcodeados en 12 ubicaciones | Centralizar |
| F5 Cognitive Router | No existe | Construir sobre el gateway existente |
| F6 Políticas de routing | No existen | Diseñar FAST/REASONING/CREATIVE/VISION/VALIDATION |
| F7 Alex White Label | AlexIO funciona pero está hardcodeado como marca | Separar engine de marca |
| F8 Cognitive Contract de Alex | Parcial — `ALEXIO_LIVE_SYSTEM_PROMPT` es el contrato actual | Expandir con tenant config |
| F9 Tool Registry | 3 tools hardcodeados en `ai_brain_service.py` | Registrar formalmente, agregar cart/checkout/order tools |
| F10 Reglas duras de Alex | Parcial — stock/precios siempre vienen del ERP (tools reales) | Formalizar como policy |
| F11 Fallback | Implementado (Gemini→Qwen en chat, Claude→Gemini→Qwen en landing) | Expandir con retry policies |
| F12 Circuit Breaker | No existe | Implementar |
| F13 Usage Logging | `_AI_CALL_LOGS` en memoria (routers/ai.py), no persiste | Crear tabla real |
| F14 Control de costos | Créditos por tenant existen, rate limit en memoria | Conectar a Redis, agregar budget por request |
| F15 Storefront | **IMPLEMENTADO** (data-driven con blocks) | UI para editar SiteConfig |
| F16 Themes | **IMPLEMENTADO** (4 temas reales con CSS tokens) | Verificación visual, agregar más temas |
| F17 Component Registry | **IMPLEMENTADO** (7 blocks en templates/blocks/) | Agregar más bloques, variants |
| F18 Alex en storefront | **IMPLEMENTADO** (widget con function calling) | Agregar tools de cart/checkout |
| F19 Landing Generator | **IMPLEMENTADO** (cascada Claude→Gemini→Qwen) | Enrutar vía Cognitive Router |
| F20 AI Site Auditor | No existe | Futuro |
| F21 Observabilidad | Logging JSON existe, no hay dashboard | Crear dashboard interno |
| F22 Seguridad multi-tenant | Implementado con caveats (ver bugs #3, #4, #6) | Fixear bugs, agregar tests de aislamiento |
| F23 Testing | 121 tests, ~106 pasan, sin CI | Agregar tests de routing + CI pipeline |
| F24 No construir todavía | — | Respetado |
| F25 Documentación | CLAUDE.md existe (extenso), sin docs/ | Este documento es el inicio |
| F26 Definition of Done | — | Checklist al final de cada fase |
| F27 Forma de trabajo | — | Fase por fase, tests entre fases |
| F28 Informe final | — | Al terminar |

---

## CONTRADICCIONES ENCONTRADAS

| Contradicción | Impacto | Opciones | Recomendación |
|---------------|---------|----------|---------------|
| `render.yaml` define Redis, código nunca lo usa | El rate limiter no funciona con múltiples workers | (A) Implementar Redis backend para slowapi (B) Quedarse con 1 worker | **(A)** cuando haya múltiples workers reales |
| `GeminiService` y `AIBrainService` usan modelos distintos para la misma tarea (chat) | Inconsistencia de calidad entre `/api/v1/ai/chat` (legacy) y `/api/v1/ai/alex-io` (brain) | (A) Eliminar GeminiService y migrar todo a BrainService (B) Mantener ambos | **(A)** a medida que se construya el Gateway |
| `frontend/` existe como Next.js pero la decisión es Jinja | Confusión para nuevos colaboradores | (A) Eliminar el directorio (B) Moverlo a un branch de referencia | **(A)** — el renderer data-driven ya reemplaza lo que el frontend iba a hacer |
| `Tax` sin `tenant_id` | Un tenant cambia la tasa y afecta a todos | (A) Agregar tenant_id a Tax (B) Mover tax_rate a Settings (ya existe ahí) | **(B)** — `Settings.tax_rate` ya existe y es per-tenant; la tabla `Tax` parece redundante |
