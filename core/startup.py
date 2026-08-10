import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import Session
from sqlalchemy import text
from database.session import engine
from services.auth_service import AuthService
from core.seed import run_seed_if_configured

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run Alembic migrations on startup
    try:
        from alembic import command
        from alembic.config import Config
        alembic_cfg = Config("alembic.ini")
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            # alembic.config.Config usa configparser por debajo, que interpreta
            # '%' como caracter de interpolacion (ej. '%(algo)s'). Si la password
            # tiene un caracter especial url-encodeado (ej. '$' -> '%24'), rompe
            # con "invalid interpolation syntax" y la migracion nunca corre.
            # Hay que escapar '%' como '%%' antes de setear la opcion.
            alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.error(f"Alembic migration failed: {e}")

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
