import os
import logging
from sqlmodel import Session
from database.seed_data import seed_products, seed_business_categories

logger = logging.getLogger(__name__)

def run_seed_if_configured(engine):
    if os.getenv("SEED_ON_START") == "1":
        try:
            with Session(engine) as session:
                seed_products(session)
                logger.info("Products seeded successfully.")
        except Exception as e:
            logger.error(f"Seed products failed: {e}")
    try:
        with Session(engine) as session:
            seed_business_categories(session)
    except Exception as e:
        logger.error(f"Seed business categories failed: {e}")
