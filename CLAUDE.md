# VibeCloud — Informe técnico y plan de ejecución

> Documento único y vigente (27/09/2026). Reemplaza al informe del 26/09 y a los prompts anteriores.
> Va en la raíz del repo como `CLAUDE.md`. Claude Code lo lee en cada sesión y ejecuta UNA fase por vez.

---

## PARTE 1 — Informe técnico

### 1.1 Qué es VibeCloud

Plataforma para comercios de **LATAM y EE. UU.** que venden online y en el mostrador con **un solo stock**, con un constructor de sitios con IA.

- Cliente inicial: comercio que ya vende (local y/o Instagram/WhatsApp).
- Idioma: español con base mexicana. Todos los textos centralizados para traducir después (inglés para EE. UU.).
- Monedas: planes en USD; cada tienda vende en la moneda del comercio.
- Estado: MVP. Deploy actual en Render (`vibecloud-backend-5iw2.onrender.com`).

### 1.2 Stack

| Capa | Hoy | Objetivo |
|---|---|---|
| Backend | FastAPI 0.109.2 + Uvicorn, Python 3.10 | FastAPI/Starlette actualizados, sin CVEs conocidos |
| ORM / DB | SQLModel, Postgres en Supabase, SQLite en dev, Alembic (29 migraciones) | Igual; tests contra Postgres en CI |
| UI | 79 templates Jinja2 | Igual. `frontend/` (React) pendiente de decidir |
| Auth | Sesiones Starlette + JWT HS256; Argon2 + bcrypt vía passlib | argon2-cffi directo; bcrypt solo para rehashear hashes viejos |
| Imágenes | Disco local (se pierden en cada deploy) | Google Cloud Storage + CDN |
| Hosting | Render | Google Cloud Run (después de la Fase 4); DB sigue en Supabase |
| Tareas lentas | Dentro del request | Cloud Tasks (al migrar a Google) |
| Pagos | No cobra; `/credits/buy` regala créditos | Pasarela por país: Mercado Pago (LATAM), Stripe (EE. UU.) |
| Monitoreo | Nada | Sentry + `/health` |
| CI/CD | Push manual | GitHub Actions: tests en Postgres + deploy solo en verde |
| Tests | 284 (282 pasan, 2 fallan en caja) | 0 fallos |

### 1.3 Planes (no hay plan gratis)

| Plan | Precio | Incluye | Créditos IA/mes | Regeneraciones | Productos | Storage | Usuarios |
|---|---|---|---|---|---|---|---|
| Inicial | US$3,97/mes | Sitio con IA, catálogo, pedidos por WhatsApp (sin checkout) | 30 | 5 | 30 | 250 MB | 1 |
| Tienda | US$19/mes | + tienda con checkout | 500 | 40 | sin límite | 2 GB | 1 |
| Comercio | US$49/mes | + POS, stock, caja, cuentas corrientes, reportes, equipo, dominio propio | 2.000 | 200 | sin límite | 10 GB | 5 |

- Límites = propuesta, se validan en la beta. Nada es ilimitado.
- Límites en UN solo modelo de plan, aplicados en el backend.
- En US$3,97 el cargo fijo de la pasarela pesa mucho: ofrecer pago anual.

### 1.4 Módulos por nivel (no se congela nada)

Todos los módulos siguen vivos. Se terminan en versión mínima y se habilitan **cuando el comercio sube de nivel o cuando el público los pide**. El desarrollo sigue el mismo orden.

| Nivel | Se habilita cuando (umbral a definir) | Módulos | Versión mínima |
|---|---|---|---|
| 1 · Arranque | Al registrarse (según plan) | Constructor de sitios (landing_studio + 4 plantillas + blocks), tienda (storefront, store), catálogo (products, catalog_import, catálogo curado), checkout (payments), POS (sales), stock (wms), caja (cash), clientes (clients), reportes (reports), equipo (team), asistente IA (ai), onboarding, contenido redes (social_content) | Completa |
| 2 · Inteligencia | Tienda publicada + primeras ventas; TimesFM además con historial suficiente | Estudio de mercado (research, competitor_service), debates (expert_debate, offer), TimesFM (timesfm) | Preguntas simples con datos verificados; debates como resumen "a favor / en contra / qué probar"; "cuánto stock pedir" |
| 3 · Comunidad | Ventas sostenidas + métricas de confianza limpias | VibeNet (network), cursos (courses), picking, CRM (crm) | Directorio + perfil sin mensajería; un curso cobrado con la pasarela; lista de preparación; export CSV de clientes |

- **Se borra (código muerto):** vars Medusa en `core/config.py`, `services/llm/`, `services/voice/`, `services/provider_factory.py`, `templates/hub.html`.
- **Pendiente de decidir (NO borrar):** `services/whatsapp_service.py` (¿lo usa ALEX IO?), `frontend/` React.

### 1.5 Pagos

| Mercado | Pasarela del comercio | Notas |
|---|---|---|
| EE. UU. | Stripe | Stripe Connect para comisión; VibeCloud necesita entidad en EE. UU. (ej. Stripe Atlas) |
| México, Brasil | Mercado Pago o Stripe | Métodos locales: OXXO (MX), PIX (BR) |
| Argentina, Chile, Colombia, Perú, Uruguay | Mercado Pago | Split marketplace |
| Más adelante | dLocal / EBANX | Un contrato para muchos países |

- Suscripciones de VibeCloud en USD (Stripe cuando exista la entidad; mientras, Mercado Pago por país).
- Takenos/DolarApp: no sirven como checkout (TakeLink no acepta pagadores de Argentina; DolarApp no tiene checkout). Posible uso: guardar dólares o cobrar suscripciones del exterior.
- **Facturación fiscal (ARCA, CFDI): la hace cada comercio por fuera y la envía por mail. La plataforma NO factura.**

### 1.6 IA

- Landings: pasar a un modelo más barato (hoy usa el más caro).
- Log por llamada: proveedor, modelo, si hubo fallback y por qué.
- Function-calling probado en toda la cascada (también en el fallback).
- Asistente de la tienda: solo `consultar_stock` y `recomendar_productos`, tope diario por tenant, `tenant_id` fijado por el servidor.
- Descuento de créditos atómico: `UPDATE ... WHERE ai_credits >= n`.
- **Estudio de mercado:** los datos se obtienen por scraping o APIs oficiales (respetando robots.txt y términos), se guardan con fuente, URL y fecha, y al menos dos LLMs verifican que la cifra aparezca en el texto de la fuente. Sin fuente verificada, no se muestra. Nunca un "% de viabilidad".

### 1.7 Seguridad (nivel MVP)

- **Mínimo obligatorio (Fase 0):** bloquear `/credits/buy`, cerrar acceso anónimo a Supabase, secretos sin defaults, filtro de tenant básico que falla cerrado, cookie SameSite=Lax, dependencias sin CVEs conocidos.
- **Después, con clientes pagando:** tests cruzados completos, CSRF completo, IP real detrás de proxy, ajustes anti-fraude, rotación de claves (MultiFernet).

### 1.8 Hosting

- Destino: **Google Cloud** (Cloud Run + Cloud Storage + Secret Manager + Cloud Tasks). Motivo: ya se usa Gemini y TimesFM, y Cloud Run es simple de operar.
- AWS también serviría; el mismo Dockerfile sirve para ambos.
- No se migra ahora: se prepara (Dockerfile, Cloud Storage) y el servidor se mueve después de la Fase 4.
- Créditos Google sin inversión: US$2.000. Los montos grandes piden etapa Seed–Serie A.

### 1.9 Errores conocidos del código propuesto por Gemini (NO copiarlo tal cual)

1. **Filtro de tenant:** lee el tenant en un middleware antes de que se resuelva (siempre vacío); deja pasar todo si no hay tenant; `filter_by` filtra mal con JOINs.
2. **Mercado Pago:** `import sdk` inexistente; idempotencia por `payment_id` descarta el aviso "approved" después del "pending"; cobra con la cuenta de la plataforma si el comercio no conectó la suya; no valida firma, monto ni moneda; `float` para dinero; ARS fijo; tokens sin cifrar.
3. **Storage:** boto3 bloqueante dentro de `async`; confía en `content_type` del cliente; keys sin tenant; expone errores internos; apunta a DigitalOcean.
4. **Celery:** reintenta ante cualquier error (vuelve a pagar la IA); usa el modelo caro; agrega Redis innecesario.
5. **CI:** ruff sin baseline + 2 tests rotos = CI rojo desde el día 1; despliega a DigitalOcean.

### 1.10 Métrica norte

Comercios pagando y activos al día 30. Objetivo de la beta: 5 a 10.

---

## PARTE 2 — Reglas para Claude Code

- Una fase = una rama = un PR. No mezclar fases.
- Antes de cambiar código: leé los archivos involucrados y mostrame un plan corto.
- Todo cambio lleva tests. `pytest` en verde.
- No marques nada como hecho si no está probado. Al final de cada fase reportá: qué cambió, qué tests agregaste, qué quedó pendiente, qué riesgos viste.
- Si algo contradice este documento, pará y preguntame.
- Nunca borres datos ni apliques migraciones destructivas sin mi confirmación.
- Dinero siempre en `Decimal`/`Numeric`.
- No agregar Redis, Celery, AWS, DigitalOcean, Vercel ni Cloudflare for SaaS salvo que la fase lo pida.

---

## PARTE 3 — Fases (ejecutar en orden, una por sesión)

### Fase 0 — Seguridad mínima del MVP
1. `/credits/buy`: bloquearlo (solo superadmin o 403 claro) hasta que exista cobro real. Test.
2. Supabase: encontrar dónde se usa la librería y las keys. Decirme si las tablas quedan expuestas por PostgREST. Proponer el SQL de RLS deny-all para `anon`/`authenticated`. NO ejecutarlo.
3. Secretos (JWT, sesión, `VIBECLOUD_API_KEY`): solo desde variables de entorno; la app no arranca en producción sin ellos.
4. Filtro de tenant básico: `tenant_id` en `session.info` desde la dependencia que crea la sesión; evento `do_orm_execute` con `with_loader_criteria(..., include_aliases=True)` para cada modelo con `tenant_id`; si no hay tenant y la query no tiene `execution_options(ignore_tenant=True)`, excepción. Loguear cada `ignore_tenant`.
5. Cookie de sesión SameSite=Lax, Secure, HttpOnly.
6. Actualizar FastAPI/Starlette/python-multipart. Si algo rompe, reportarlo.
7. IA: listar los IDs de modelo usados y agregar el log por llamada (proveedor, modelo, fallback, motivo).

### Fase 1 — Niveles y limpieza
1. `services/entitlements.py`: único lugar que responde "¿este tenant puede usar el módulo X?" combinando plan + nivel. Los `has_*` se derivan de ahí.
2. Nivel guardado en `Tenant` (nivel + fecha). Reglas de subida configurables con umbrales editables.
3. Módulo no habilitado → 403 con mensaje "Se habilita cuando…"; en el menú aparece bloqueado con su requisito.
4. Jobs o llamadas de IA de módulos no habilitados no deben correr ni gastar créditos.
5. Borrar el código muerto de 1.4 (confirmar con grep antes). NO borrar whatsapp_service.py ni frontend/.
6. Reportar en qué nivel quedaría cada tenant existente (solo lectura), para no quitarle a nadie algo que ya usa.

### Fase 2 — CI, tests y contenedor
1. Arreglar los 2 tests de caja. Decir si el bug es del código o del test y su impacto en dinero.
2. GitHub Actions: Postgres 15 como servicio, `alembic upgrade head`, pytest, ruff con baseline (que no arranque en rojo). Deploy hook de Render solo si main está en verde.
3. Reemplazar passlib por argon2-cffi (bcrypt solo para verificar hashes viejos y rehashear).
4. Dockerfile de producción (uvicorn `--proxy-headers`, puerto por `PORT`) y build en CI.
5. Endpoints `async def` con llamadas bloqueantes: pasarlos a `def` o a threadpool.
6. Textos de la interfaz centralizados (base para español mexicano / inglés).

### Fase 3 — Pagos
1. Interfaz `PaymentProvider` con dos implementaciones: Mercado Pago y Stripe. Empezar por la del país de los primeros clientes.
2. Cuenta del comercio conectada por OAuth (MP) o Connect (Stripe). Tokens cifrados. Sin cuenta conectada, sin checkout. Nunca cobrar con la cuenta de la plataforma.
3. Checkout con monto en `Decimal` y moneda del tenant; `external_reference` no adivinable; comisión (`marketplace_fee` / application fee) según plan, donde la pasarela lo permita.
4. Webhook público (sin JWT ni CSRF): validar firma; consultar el pago en la API; verificar monto, moneda, vendedor y tenant; idempotencia sobre la **transición de estado** (no solo el id del pago); índice UNIQUE en `ProcessedWebhook`.
5. Estados: pending → paid → failed/cancelled → refunded/charged_back. Cancelación y reembolso devuelven stock.
6. Suscripciones de VibeCloud en USD (Inicial/Tienda/Comercio). Plan y créditos se activan SOLO por webhook. Rehabilitar `/credits/buy` con este flujo.
7. Tests con respuestas mockeadas: aprobado, rechazado, duplicado, fuera de orden, monto adulterado, venta de otro tenant. Solo sandbox.

### Fase 4 — Storage, backups y monitoreo
1. Google Cloud Storage detrás de una interfaz propia: validar imagen con Pillow y re-encodear (sin EXIF/GPS); límite por plan; key `tenants/{tenant_id}/{tipo}/{uuid}.{ext}`; subida en threadpool; sin errores internos al cliente; registro de archivos por tenant.
2. Script de migración de `static/images` al bucket, con dry-run.
3. Backups: verificar retención de Supabase + pg_dump diario a bucket separado. Documentar y probar la restauración en `docs/restore.md`.
4. Sentry + `/health` que verifique la base.

### Fase 5 — Planes y límites
1. Modelo `Plan` con los límites de 1.3. Aplicados en backend.
2. Descuento de créditos atómico.
3. Landings con modelo más barato: comparar costo y calidad con 5 landings antes y después.
4. Pantalla "Mi plan" con uso y botón de upgrade.

### Fase 6 — Onboarding y estudio de mercado
1. Onboarding de 3 pasos: datos del negocio → sitio con IA → 5 productos (manual o Excel). Meta: tienda publicada en una sesión.
2. Estudio de mercado (nivel 2): preguntas en lenguaje simple; datos por scraping/APIs oficiales guardados con fuente, URL y fecha; verificación por al menos dos LLMs de que la cifra está en la fuente; sin fuente verificada no se muestra.
3. Eventos del embudo: registro, sitio generado, primer producto, tienda publicada, checkout conectado, primer pago, activo día 30.

### Fase 7 — Migrar el servidor a Google Cloud Run (después de la Fase 3)
1. Cloud Run en región cercana (São Paulo o Santiago), Secret Manager, cuenta de servicio con permisos mínimos.
2. Deploy desde GitHub Actions con la imagen del Dockerfile.
3. Landings, emails y métricas a Cloud Tasks.
4. `max-instances=1` al inicio (el rate limit en memoria no se comparte entre instancias).
5. Staging, smoke tests, cambio de DNS, Render activo 7 días como vuelta atrás.
6. Reportar costo mensual estimado vs Render.

### Checklist antes de la beta
- [ ] Fases 0 a 5 mergeadas con CI en verde
- [ ] Una compra real de punta a punta con tu propia tarjeta
- [ ] Restauración de backup probada
- [ ] Pasarela elegida para el país de los primeros clientes
- [ ] Lista de 10 comercios a contactar
