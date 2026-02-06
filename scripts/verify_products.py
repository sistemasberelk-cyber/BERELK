import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, create_engine, select
from database.models import Product

sqlite_file_name = "nexpos.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

with Session(engine) as session:
    products = session.exec(select(Product)).all()
    print(f"Total Products: {len(products)}")
    for p in products:
        print(f"ID: {p.id}, Name: {p.name}, Item#: {p.item_number}, Price: {p.price}, Barcode: {p.barcode}")
