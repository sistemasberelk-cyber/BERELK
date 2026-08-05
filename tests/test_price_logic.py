"""tests/test_price_logic.py — Tests para la lógica de precios y bultos con Decimal"""
import pytest
from decimal import Decimal
from sqlmodel import Session, SQLModel, create_engine
from database.models import Product, Sale, Tenant, Location, Bin
from services.stock_service import StockService

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_price_bulk_logic(session):
    tenant = Tenant(name="Test Tenant")
    session.add(tenant)
    session.commit()

    location = Location(tenant_id=tenant.id, name="Depósito Central", code="DEP1")
    session.add(location)
    session.commit()

    bin_ = Bin(tenant_id=tenant.id, location_id=location.id, name="SIN-UBICACION")
    session.add(bin_)
    session.commit()
    
    product = Product(
        tenant_id=tenant.id,
        name="Test Product",
        barcode="123",
        price=Decimal("100.00"),
        price_bulk=Decimal("80.00"),
        cant_bulto=10
    )
    session.add(product)
    session.commit()
    
    service = StockService()
    service.add_stock(session, product.id, tenant.id, 100, "ingreso", "Stock inicial")
    
    sale1 = service.process_sale(session, user_id=1, tenant_id=tenant.id, items_data=[{"product_id": product.id, "quantity": 5}])
    assert sale1.items[0].unit_price == Decimal("100.00")
    assert sale1.total_amount == Decimal("500.00")
    
    sale2 = service.process_sale(session, user_id=1, tenant_id=tenant.id, items_data=[{"product_id": product.id, "quantity": 10}])
    assert sale2.items[0].unit_price == Decimal("80.00")
    assert sale2.total_amount == Decimal("800.00")
    
    product2 = Product(tenant_id=tenant.id, name="P2", barcode="456", price=Decimal("50.00"))
    session.add(product2)
    session.commit()
    service.add_stock(session, product2.id, tenant.id, 10, "ingreso", "Stock inicial")
    
    sale3 = service.process_sale(session, user_id=1, tenant_id=tenant.id, items_data=[{"product_id": product2.id, "quantity": 5}])
    assert sale3.items[0].unit_price == Decimal("50.00")
