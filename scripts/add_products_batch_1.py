import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, create_engine, select
from database.models import Product
from services.stock_service import StockService

# Connect to DB
sqlite_file_name = "nexpos.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)
stock_service = StockService()

products_data = [
    {
        "item_number": "7111",
        "name": "Gomon Pin Negro",
        "price": 7500.0,
        "numeracion": "35-40",
        "cant_bulto": 12,
        "stock_quantity": 100, # Default
        "category": "Verano"
    },
    {
        "item_number": "7110",
        "name": "Articulo 7110",
        "price": 13000.0,
        "numeracion": "35-40",
        "cant_bulto": 12,
        "stock_quantity": 100,
        "category": "Verano"
    },
    {
        "item_number": "7098",
        "name": "Gomon NO Pin",
        "price": 6000.0,
        "numeracion": "35-40",
        "cant_bulto": 12, # 12 Ps
        "stock_quantity": 100,
        "category": "Verano"
    },
    {
        "item_number": "7083",
        "name": "1/2 Alto",
        "price": 8500.0,
        "numeracion": "35-40",
        "cant_bulto": 12, # 12 Surt
        "stock_quantity": 100,
        "category": "Verano"
    },
    {
        "item_number": "7091",
        "name": "Articulo 7091",
        "price": 7200.0,
        "numeracion": "35/6-39/0",
        "cant_bulto": 12, # 12 p. Sur
        "stock_quantity": 100,
        "category": "Verano"
    }
]

with Session(engine) as session:
    for p_data in products_data:
        # Check if exists
        item_num = p_data["item_number"]
        existing = session.exec(select(Product).where(Product.item_number == item_num)).first()
        
        if existing:
            print(f"Updating {item_num}")
            existing.price = p_data["price"]
            existing.name = p_data["name"]
            existing.numeracion = p_data["numeracion"]
            existing.cant_bulto = p_data["cant_bulto"]
            session.add(existing)
        else:
            print(f"Creating {item_num}")
            new_prod = Product(**p_data)
            
            # Generate barcode?
            if not new_prod.barcode:
                 # Use Item Number as barcode if it's numeric/EAN compatible, else generate a placeholder to allow insert
                 # The constraint is NOT NULL.
                 # If we use generate_barcode(id), we need the ID first.
                 # Strategy: Insert with temp barcode, then update? Or generate a random one?
                 # Service expects ID. 
                 # Let's use item_number as barcode for now if possible.
                 if item_num and item_num.isdigit():
                     new_prod.barcode = item_num
                 else:
                     import uuid
                     new_prod.barcode = str(uuid.uuid4())[:12] # temp
                 
            session.add(new_prod)
            session.commit()
            session.refresh(new_prod)
            
            # Now generate real barcode if needed/wanted
            # If we used a temp uuid, maybe we want to keep it or generate a specific one.
            # StockService.generate_barcode uses ID.
            if len(new_prod.barcode) == 36 or new_prod.barcode == item_num: # If we used temp
                # Optional: Generate file
                try: 
                    # stock_service.generate_barcode generates a file AND returns the filename? 
                    # No, it returns filename. It uses ID.
                    # It doesn't update the DB object.
                    # We might want to overwrite the barcode field with the generated code (string)
                    # wait, generate_barcode uses "code128" with the ID padded.
                    # Let's stick with item_number as barcode if digit, else generate.
                    pass
                except:
                    pass
                
        session.commit()

print("Products processed.")
