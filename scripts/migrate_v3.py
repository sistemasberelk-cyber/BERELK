import sys
import os

# Add parent directory to path to allow importing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, create_engine, text
from database.models import *

# Database URL (assuming SQLite)
sqlite_file_name = "nexpos.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

def migrate():
    print("Starting Migration...")
    with Session(engine) as session:
        # Alter Statements
        statements = [
            # Product
            "ALTER TABLE product ADD COLUMN item_number TEXT;",
            
            # Sale
            "ALTER TABLE sale ADD COLUMN amount_paid FLOAT DEFAULT 0;",
            "ALTER TABLE sale ADD COLUMN payment_status TEXT DEFAULT 'paid';", # Default to paid for existing sales to be safe? Or pending? 'paid' is safer for old sales usually.
            
            # Client (just in case they weren't run before)
            "ALTER TABLE client ADD COLUMN cuit TEXT;",
            "ALTER TABLE client ADD COLUMN iva_category TEXT;",
            "ALTER TABLE client ADD COLUMN transport_name TEXT;",
            "ALTER TABLE client ADD COLUMN transport_address TEXT;"
        ]
        
        for stmt in statements:
            try:
                session.exec(text(stmt))
                session.commit()
                print(f"Executed: {stmt}")
            except Exception as e:
                print(f"Skipped (probably exists): {stmt} -> {e}")
                
    print("Migration Finished.")

if __name__ == "__main__":
    migrate()
