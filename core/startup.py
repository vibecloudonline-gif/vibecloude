import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import Session
from sqlalchemy import text, inspect
from database.session import engine, create_db_and_tables
from services.auth_service import AuthService
from core.seed import run_seed_if_configured

logger = logging.getLogger(__name__)


def _repair_schema(eng):
    """Fix columns/tables that stamp-head skipped.

    When a previous deploy ran stamp('head') without actually executing the
    migrations, existing tables are missing new columns. create_db_and_tables
    only creates missing tables (CREATE TABLE IF NOT EXISTS), it never ALTERs
    existing ones.  This function adds known missing columns idempotently.
    """
    inspector = inspect(eng)
    existing_tables = set(inspector.get_table_names())

    with eng.begin() as conn:
        if "settings" in existing_tables:
            cols = {c["name"] for c in inspector.get_columns("settings")}
            if "site_config_json" not in cols:
                conn.execute(text("ALTER TABLE settings ADD COLUMN site_config_json TEXT"))
                logger.warning("schema_repair: added settings.site_config_json")

        if "platformpayment" not in existing_tables:
            create_db_and_tables()
            logger.warning("schema_repair: ran create_db_and_tables for missing tables")
            existing_tables = set(inspect(eng).get_table_names())

        for tbl in [
            "researchproject", "researchlisting", "researchdemand",
            "competitoranalysis", "offer", "validationdebate",
            "debateobjection",
        ]:
            if tbl not in existing_tables:
                create_db_and_tables()
                logger.warning("schema_repair: ran create_db_and_tables for missing table %s", tbl)
                break


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = None
    try:
        from alembic import command
        from alembic.config import Config
        alembic_cfg = Config("alembic.ini")
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error(f"Alembic migration failed: {e}")
        try:
            create_db_and_tables()
            if alembic_cfg is not None:
                command.stamp(alembic_cfg, "head")
            logger.warning(
                "Se creo el esquema directo desde los modelos (create_db_and_tables) "
                "y se marco la base como al dia con Alembic (stamp head)."
            )
        except Exception as e2:
            logger.error(f"Fallback create_db_and_tables tambien fallo: {e2}")

    try:
        _repair_schema(engine)
    except Exception as e:
        logger.error(f"Schema repair failed (non-fatal): {e}")

    try:
        with Session(engine) as session:
            try:
                AuthService.create_default_user_and_settings(session)
            except Exception as e:
                session.rollback()
                logger.error(f"AuthService setup failed (non-fatal): {e}")
            run_seed_if_configured(engine)
    except Exception as e:
        logger.error(f"Session setup failed (non-fatal): {e}")

    # Start background daily theme scheduler
    try:
        import asyncio
        from web.scheduler import theme_scheduler_loop
        asyncio.ensure_future(theme_scheduler_loop())
        logger.info("Theme scheduler started.")
    except Exception as e:
        logger.error(f"Theme scheduler failed to start (non-fatal): {e}")

    yield
