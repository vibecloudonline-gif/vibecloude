-- =============================================================================
-- RLS deny-all para Supabase — VibeCloud Fase 0
-- =============================================================================
-- PROPÓSITO: Cerrar el acceso anónimo vía PostgREST a TODAS las tablas.
-- Supabase expone un endpoint REST (PostgREST) que permite SELECT/INSERT/UPDATE/DELETE
-- a cualquier tabla que NO tenga RLS habilitado, usando la key "anon" o "authenticated".
--
-- VibeCloud accede a Postgres por conexión directa (SQLAlchemy), NO por PostgREST.
-- Por lo tanto, el acceso vía PostgREST debe estar COMPLETAMENTE bloqueado.
--
-- INSTRUCCIONES:
--   1. Ejecutar este SQL en el SQL Editor de Supabase Dashboard.
--   2. Verificar que la app sigue funcionando (usa conexión directa, no PostgREST).
--   3. NO dar rollback a menos que algo falle.
--
-- IMPORTANTE: Este SQL NO afecta la conexión directa de SQLAlchemy (usa el role
-- "postgres" que es superusuario y bypasea RLS automáticamente).
-- =============================================================================

-- Tablas con tenant_id (datos multi-tenant sensibles)
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenantdomain ENABLE ROW LEVEL SECURITY;
ALTER TABLE supportticket ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenantprofile ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE tax ENABLE ROW LEVEL SECURITY;
ALTER TABLE client ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user" ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenantcatalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE landingpage ENABLE ROW LEVEL SECURITY;
ALTER TABLE product ENABLE ROW LEVEL SECURITY;
ALTER TABLE syncqueue ENABLE ROW LEVEL SECURITY;
ALTER TABLE processedwebhook ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale ENABLE ROW LEVEL SECURITY;
ALTER TABLE saleitem ENABLE ROW LEVEL SECURITY;
ALTER TABLE paymentallocation ENABLE ROW LEVEL SECURITY;
ALTER TABLE accountreceivable ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchaseitem ENABLE ROW LEVEL SECURITY;
ALTER TABLE cashmovement ENABLE ROW LEVEL SECURITY;
ALTER TABLE location ENABLE ROW LEVEL SECURITY;
ALTER TABLE bin ENABLE ROW LEVEL SECURITY;
ALTER TABLE binstock ENABLE ROW LEVEL SECURITY;
ALTER TABLE stockmovement ENABLE ROW LEVEL SECURITY;
ALTER TABLE businessconfig ENABLE ROW LEVEL SECURITY;
ALTER TABLE aicredential ENABLE ROW LEVEL SECURITY;
ALTER TABLE refreshtoken ENABLE ROW LEVEL SECURITY;
ALTER TABLE platformpayment ENABLE ROW LEVEL SECURITY;
ALTER TABLE uiconfig ENABLE ROW LEVEL SECURITY;
ALTER TABLE researchproject ENABLE ROW LEVEL SECURITY;
ALTER TABLE researchlisting ENABLE ROW LEVEL SECURITY;
ALTER TABLE researchdemand ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitoranalysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE offer ENABLE ROW LEVEL SECURITY;
ALTER TABLE validationdebate ENABLE ROW LEVEL SECURITY;
ALTER TABLE debateobjection ENABLE ROW LEVEL SECURITY;
ALTER TABLE expertdebate ENABLE ROW LEVEL SECURITY;
ALTER TABLE expertopinion ENABLE ROW LEVEL SECURITY;
ALTER TABLE researchforecast ENABLE ROW LEVEL SECURITY;
ALTER TABLE forecastprofile ENABLE ROW LEVEL SECURITY;
ALTER TABLE course ENABLE ROW LEVEL SECURITY;
ALTER TABLE lesson ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrollment ENABLE ROW LEVEL SECURITY;
ALTER TABLE lessonprogress ENABLE ROW LEVEL SECURITY;
ALTER TABLE businesscategory ENABLE ROW LEVEL SECURITY;
ALTER TABLE businessprofile ENABLE ROW LEVEL SECURITY;
ALTER TABLE connection ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation ENABLE ROW LEVEL SECURITY;
ALTER TABLE netmessage ENABLE ROW LEVEL SECURITY;
ALTER TABLE businessreview ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedpost ENABLE ROW LEVEL SECURITY;
ALTER TABLE crmsynclog ENABLE ROW LEVEL SECURITY;
ALTER TABLE orderfingerprint ENABLE ROW LEVEL SECURITY;
ALTER TABLE returnrequest ENABLE ROW LEVEL SECURITY;
ALTER TABLE trustmetrics ENABLE ROW LEVEL SECURITY;

-- Tabla de migraciones de Alembic (no tiene tenant_id pero tampoco debe exponerse)
ALTER TABLE alembic_version ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- Con RLS habilitado y SIN políticas definidas, el comportamiento default de
-- Postgres es DENY ALL para los roles anon y authenticated.
-- El role "postgres" (usado por SQLAlchemy) es superusuario y bypasea RLS.
--
-- Si en el futuro se necesita acceso por PostgREST (ej: para una app mobile),
-- crear políticas explícitas por tabla con:
--   CREATE POLICY "tenant_isolation" ON <tabla>
--     USING (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id')
--     WITH CHECK (tenant_id = current_setting('request.jwt.claims')::json->>'tenant_id');
-- =============================================================================

-- Verificación: listar tablas sin RLS (debería devolver 0 filas después de ejecutar)
-- SELECT schemaname, tablename, rowsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public' AND rowsecurity = false;
