"""scripts/backup_db.py — Backup de la base de datos a GCS.

Uso:
    python scripts/backup_db.py                    # pg_dump + sube a GCS
    python scripts/backup_db.py --local-only       # pg_dump local, sin subir
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Backup pg_dump a GCS")
    parser.add_argument("--local-only", action="store_true", help="Solo dump local")
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL no configurada")
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dump_file = f"backup_{ts}.sql.gz"

    print(f"Dumping database to {dump_file}...")
    result = subprocess.run(
        f'pg_dump "{db_url}" | gzip > {dump_file}',
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR pg_dump: {result.stderr}")
        sys.exit(1)

    size = os.path.getsize(dump_file)
    print(f"Dump OK: {dump_file} ({size / 1024 / 1024:.1f} MB)")

    if args.local_only:
        print("--local-only: no se sube a GCS")
        return

    bucket = os.getenv("GCS_BACKUP_BUCKET", "")
    if not bucket:
        print("GCS_BACKUP_BUCKET no configurado — backup queda local")
        return

    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        b = client.bucket(bucket)
        blob = b.blob(f"db-backups/{dump_file}")
        blob.upload_from_filename(dump_file)
        print(f"Subido a gs://{bucket}/db-backups/{dump_file}")
        os.remove(dump_file)
    except Exception as e:
        print(f"Error subiendo a GCS: {e}")
        print(f"Backup local conservado: {dump_file}")


if __name__ == "__main__":
    main()
