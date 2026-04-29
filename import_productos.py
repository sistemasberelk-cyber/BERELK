import sys
import pandas as pd
from sqlmodel import Session, select
from database.session import engine, create_db_and_tables
from database.models import Product, Tenant, User, Settings
from services.auth_service import AuthService
import math

def generate_barcode_for_id(pid: int) -> str:
    return f"779{pid:09d}0"

def run_import():
    print("Initializing Database...")
    create_db_and_tables()

    print("Reading Excel...")
    df = pd.read_excel('productos.xlsx')
    
    products_added = 0
    with Session(engine) as session:
        # Ensure default tenant exists
        AuthService.create_default_user_and_settings(session)
        tenant = session.exec(select(Tenant)).first()
        if not tenant:
            print("Error: Could not obtain a default tenant.")
            sys.exit(1)

        for idx, row in df.iterrows():
            name = str(row.get('Name', ''))
            if not name or name == 'nan':
                 continue
                 
            try:
                price = float(row.get('Price', 0))
                if math.isnan(price): price = 0
            except:
                price = 0
                
            try:
                stock = int(row.get('Stock', 0))
                if math.isnan(stock): stock = 0
            except:
                stock = 0
                
            category = str(row.get('Category', ''))
            if category == 'nan': category = ""
            
            item_num = str(row.get('ItemNumber', ''))
            if item_num == 'nan': item_num = ""
            
            desc = str(row.get('Description', ''))
            if desc == 'nan': desc = ""
            
            numeracion = str(row.get('Numeracion', ''))
            if numeracion == 'nan': numeracion = ""
            
            try:
                cant_bulto = int(row.get('CantBulto', 1))
                if math.isnan(cant_bulto): cant_bulto = 1
            except:
                cant_bulto = 1
                
            barcode_val = str(row.get('Barcode', ''))
            if barcode_val == 'nan' or not barcode_val:
                barcode_val = ""
            
            try:
                price_bulk = float(row.get('PriceBulk', 0))
                if math.isnan(price_bulk): price_bulk = price
            except:
                price_bulk = price
                
            product = Product(
                tenant_id=tenant.id,
                name=name,
                price=price,
                stock_quantity=stock,
                category=category,
                item_number=item_num,
                description=desc,
                numeracion=numeracion,
                cant_bulto=cant_bulto,
                barcode=barcode_val,
                price_bulk=price_bulk,
                price_retail=price
            )
            session.add(product)
            session.commit()
            session.refresh(product)
            
            if not product.barcode:
                product.barcode = generate_barcode_for_id(product.id)
                session.add(product)
                session.commit()
                
            products_added += 1

    print(f"✅ Successfully added {products_added} products to the database.")

if __name__ == '__main__':
    run_import()
