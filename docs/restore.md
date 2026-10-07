# Restauración de backup — VibeCloud

## Fuentes de backup

### 1. Supabase (automático)
- Retención: 7 días en plan Free, 30 días en Pro.
- Acceso: Dashboard Supabase → Database → Backups → Download.
- Formato: pg_dump SQL plano.

### 2. GCS (script diario)
- Ubicación: `gs://{GCS_BACKUP_BUCKET}/db-backups/backup_YYYYMMDD_HHMMSS.sql.gz`
- Generado por `scripts/backup_db.py` (ejecutar manualmente o via cron/Cloud Scheduler).

## Procedimiento de restauración

### Desde Supabase
1. Descargar el backup desde el dashboard.
2. Crear una nueva base o limpiar la existente:
   ```bash
   psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
   ```
3. Restaurar:
   ```bash
   psql $DATABASE_URL < backup_file.sql
   ```

### Desde GCS
1. Descargar:
   ```bash
   gsutil cp gs://BUCKET/db-backups/backup_YYYYMMDD_HHMMSS.sql.gz .
   ```
2. Descomprimir y restaurar:
   ```bash
   gunzip backup_*.sql.gz
   psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
   psql $DATABASE_URL < backup_*.sql
   ```

### Después de restaurar
1. Verificar migraciones:
   ```bash
   alembic current
   alembic upgrade head  # aplica migraciones faltantes
   ```
2. Verificar datos:
   ```bash
   psql $DATABASE_URL -c "SELECT count(*) FROM tenant;"
   ```
3. Verificar la app:
   ```bash
   curl http://localhost:8000/health
   ```

## Verificación periódica
- Cada 30 días: restaurar un backup en una DB temporal y verificar que la app arranca.
- Comando rápido:
  ```bash
  createdb vibecloud_restore_test
  psql vibecloud_restore_test < backup.sql
  DATABASE_URL=postgresql://localhost/vibecloud_restore_test python -c "from database.session import engine; engine.connect()"
  dropdb vibecloud_restore_test
  ```
