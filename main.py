from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from contextlib import asynccontextmanager
from typing import List

from database.session import create_db_and_tables, get_session
from database.models import Product, Sale, User
from services.stock_service import StockService

# Setup
stock_service = StockService(static_dir="static/barcodes")
templates = Jinja2Templates(directory="templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    create_db_and_tables()
    yield

app = FastAPI(title="StockApp Professional", lifespan=lifespan)

# Mount Static Files (CSS, JS, Barcodes)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- API Endpoints ---

@app.get("/api/products", response_model=List[Product])
def get_products_api(session: Session = Depends(get_session)):
    return session.exec(select(Product)).all()

@app.post("/api/products")
def create_product_api(
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    session: Session = Depends(get_session)
):
    product = Product(name=name, price=price, stock_quantity=stock, barcode="")
    session.add(product)
    session.commit()
    session.refresh(product)
    
    # Generate Barcode
    barcode_img = stock_service.generate_barcode(product.id)
    product.barcode = barcode_img
    session.add(product)
    session.commit()
    
    return product

@app.post("/api/sales")
def create_sale_api(
    sale_data: dict, # JSON Body: {"items": [{"product_id": 1, "quantity": 1}]}
    session: Session = Depends(get_session)
):
    try:
        # Hardcoded user_id=1 for now
        sale = stock_service.process_sale(session, user_id=1, items_data=sale_data["items"])
        return sale
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Frontend Routes ---

@app.get("/", response_class=HTMLResponse)
def get_dashboard(request: Request, session: Session = Depends(get_session)):
    # Calculate stats
    total_products = session.exec(select(func.count(Product.id))).one()
    low_stock = session.exec(select(func.count(Product.id)).where(Product.stock_quantity < Product.min_stock_level)).one()
    recent_sales = session.exec(select(Sale).order_by(Sale.timestamp.desc()).limit(5)).all()
    
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "active_page": "home",
            "total_products": total_products,
            "low_stock": low_stock,
            "recent_sales": recent_sales
        }
    )

@app.get("/pos", response_class=HTMLResponse)
def get_pos(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="pos.html", 
        context={"active_page": "pos"}
    )

@app.get("/products", response_class=HTMLResponse)
def get_products_page(request: Request, session: Session = Depends(get_session)):
    products = session.exec(select(Product)).all()
    return templates.TemplateResponse(
        request=request, 
        name="products.html", 
        context={"active_page": "products", "products": products} 
    )
