import os
import logging
from sqlmodel import Session
from database.seed_data import seed_products

logger = logging.getLogger(__name__)

def run_seed_if_configured(engine):
    if os.getenv("SEED_ON_START") == "1":
        try:
            with Session(engine) as session:
                seed_products(session)
                logger.info("Products seeded successfully.")
        except Exception as e:
            logger.error(f"Seed products failed: {e}")
