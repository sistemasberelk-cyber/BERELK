import pytest
from unittest.mock import AsyncMock, patch
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
from database.models import Tenant, User, Product, BinStock, Bin, Location, Sale
from services.ai_brain_service import ai_brain_service
from datetime import datetime

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.mark.anyio
async def test_execute_tool_consultar_stock_injection(session):
    # Setup Tenant 1 and Tenant 2
    t1 = Tenant(name="Tenant 1", subdomain="t1")
    t2 = Tenant(name="Tenant 2", subdomain="t2")
    session.add(t1)
    session.add(t2)
    session.commit()

    # Setup Product in Tenant 1 and Tenant 2
    p1 = Product(tenant_id=t1.id, name="Coca Cola", barcode="111", price=100.0)
    p2 = Product(tenant_id=t2.id, name="Pepsi", barcode="222", price=90.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    # Setup Locations and Bins
    loc1 = Location(tenant_id=t1.id, name="Loc 1")
    loc2 = Location(tenant_id=t2.id, name="Loc 2")
    session.add(loc1)
    session.add(loc2)
    session.commit()

    bin1 = Bin(tenant_id=t1.id, location_id=loc1.id, name="Bin 1")
    bin2 = Bin(tenant_id=t2.id, location_id=loc2.id, name="Bin 2")
    session.add(bin1)
    session.add(bin2)
    session.commit()

    bs1 = BinStock(tenant_id=t1.id, bin_id=bin1.id, product_id=p1.id, quantity=50)
    bs2 = BinStock(tenant_id=t2.id, bin_id=bin2.id, product_id=p2.id, quantity=30)
    session.add(bs1)
    session.add(bs2)
    session.commit()

    # Test tool execution for t1 on product p1
    res1 = await ai_brain_service._execute_tool(session, tenant_id=t1.id, name="consultar_stock", args={"product_id": p1.id})
    assert "error" not in res1
    assert res1["total_stock"] == 50
    assert res1["name"] == "Coca Cola"

    # Test cross-tenant security: t1 trying to consult t2's product p2.id
    # Regla 1.1: El model llama a consultar_stock(product_id=p2.id) pero como se inyecta tenant_id=t1.id
    # el backend debe retornar error indicando que no pertenece a su tenant.
    res_cross = await ai_brain_service._execute_tool(session, tenant_id=t1.id, name="consultar_stock", args={"product_id": p2.id})
    assert "error" in res_cross
    assert "not found or access denied" in res_cross["error"].lower()

@pytest.mark.anyio
async def test_execute_tool_obtener_metricas_ventas_isolation(session):
    # Setup Tenant 1 and Tenant 2
    t1 = Tenant(name="Tenant 1", subdomain="t1")
    t2 = Tenant(name="Tenant 2", subdomain="t2")
    session.add(t1)
    session.add(t2)
    session.commit()

    # Setup Sales for Tenant 1 and Tenant 2 on the same day
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    s1 = Sale(tenant_id=t1.id, total_amount=1500.0, timestamp=now)
    s2 = Sale(tenant_id=t2.id, total_amount=2500.0, timestamp=now)
    session.add(s1)
    session.add(s2)
    session.commit()

    # Test tools for Tenant 1
    res = await ai_brain_service._execute_tool(session, tenant_id=t1.id, name="obtener_metricas_ventas", args={"fecha": date_str})
    assert "error" not in res
    assert res["total_sales_amount"] == 1500.0
    assert res["sales_count"] == 1
