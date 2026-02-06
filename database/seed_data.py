from sqlmodel import Session, select
from database.models import Product

def seed_products(session: Session):
    products_data = [
        {
            "item_number": "7111",
            "name": "Gomon Pin Negro",
            "description": "Gomon Pin Negro - 35 al 40 - 12 Pares",
            "price": 7500.0,
            "numeracion": "35 al 40",
            "cant_bulto": 12,
            "stock_quantity": 120, # Default stock
            "barcode": "711100000001", # generated dummy barcode
            "category": "Calzado"
        },
        {
            "item_number": "7098",
            "name": "Gomon NO Pin",
            "description": "Gomon NO Pin - 35 al 40 - 12 Pares",
            "price": 6000.0,
            "numeracion": "35 al 40",
            "cant_bulto": 12,
            "stock_quantity": 120,
            "barcode": "709800000001",
            "category": "Calzado"
        },
        {
            "item_number": "7110",
            "name": "Articulo 7110",
            "description": "Art 7110 - 35 al 40 - 12 Pares",
            "price": 13000.0,
            "numeracion": "35 al 40",
            "cant_bulto": 12,
            "stock_quantity": 120,
            "barcode": "711000000001",
            "category": "Calzado"
        },
        {
            "item_number": "7083",
            "name": "Gomon 1/2 Alto",
            "description": "1/2 Alto - 35 al 40 - 12 Surtido",
            "price": 8500.0,
            "numeracion": "35 al 40",
            "cant_bulto": 12,
            "stock_quantity": 120,
            "barcode": "708300000001",
            "category": "Calzado"
        },
        {
            "item_number": "7091",
            "name": "Articulo 7091",
            "description": "Art 7091 - 35/6 al 39/0 - 12 Pares Surtidos",
            "price": 7200.0,
            "numeracion": "35/6 al 39/0",
            "cant_bulto": 12,
            "stock_quantity": 120,
            "barcode": "709100000001",
            "category": "Calzado"
        }
    ]

    for p_data in products_data:
        # Check if exists by item_number
        statement = select(Product).where(Product.item_number == p_data["item_number"])
        results = session.exec(statement)
        product = results.first()

        if not product:
            new_product = Product(**p_data)
            session.add(new_product)
            print(f"Adding product: {p_data['name']}")
    
    session.commit()
