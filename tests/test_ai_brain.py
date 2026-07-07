import pytest
import json
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app
from database.session import get_session
from database.models import Tenant, User, Product, BinStock, Bin, Location, Sale, UIConfig
from services.ai_brain_service import ai_brain_service
from routers.ai import sanitize_css_property
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

@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.mark.anyio
async def test_execute_tool_consultar_stock_injection(session):
    t1 = Tenant(name="Tenant 1", subdomain="t1", ai_credits=100)
    t2 = Tenant(name="Tenant 2", subdomain="t2", ai_credits=100)
    session.add(t1)
    session.add(t2)
    session.commit()

    p1 = Product(tenant_id=t1.id, name="Coca Cola", barcode="111", price=100.0)
    p2 = Product(tenant_id=t2.id, name="Pepsi", barcode="222", price=90.0)
    session.add(p1)
    session.add(p2)
    session.commit()

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

    res1 = await ai_brain_service._execute_tool(session, tenant_id=t1.id, name="consultar_stock", args={"product_id": p1.id})
    assert "error" not in res1
    assert res1["total_stock"] == 50

    res_cross = await ai_brain_service._execute_tool(session, tenant_id=t1.id, name="consultar_stock", args={"product_id": p2.id})
    assert "error" in res_cross
    assert "not found or access denied" in res_cross["error"].lower()

@pytest.mark.anyio
async def test_execute_tool_obtener_metricas_ventas_isolation(session):
    t1 = Tenant(name="Tenant 1", subdomain="t1")
    t2 = Tenant(name="Tenant 2", subdomain="t2")
    session.add(t1)
    session.add(t2)
    session.commit()

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    s1 = Sale(tenant_id=t1.id, total_amount=1500.0, timestamp=now)
    s2 = Sale(tenant_id=t2.id, total_amount=2500.0, timestamp=now)
    session.add(s1)
    session.add(s2)
    session.commit()

    res = await ai_brain_service._execute_tool(session, tenant_id=t1.id, name="obtener_metricas_ventas", args={"fecha": date_str})
    assert "error" not in res
    assert res["total_sales_amount"] == 1500.0

@pytest.mark.anyio
async def test_alex_io_route_successful(client, session, monkeypatch):
    t1 = Tenant(name="Tenant 1", subdomain="t1", ai_credits=100)
    session.add(t1)
    session.commit()

    mock_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Hola, el stock es de 50."}]
                }
            }
        ]
    }

    async def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_response_data
        return mock_resp

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    payload = {
        "history": [],
        "new_message": "Hola Alex",
        "system_instruction": "Test"
    }

    response = client.post(
        "/api/v1/ai/alex-io",
        headers={"x-tenant-subdomain": "t1"},
        json=payload
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    db_tenant = session.get(Tenant, t1.id)
    assert db_tenant.ai_credits == 99

@pytest.mark.anyio
async def test_alex_io_insufficient_credits(client, session):
    t1 = Tenant(name="Tenant 1", subdomain="t1", ai_credits=0)
    session.add(t1)
    session.commit()

    payload = {
        "history": [],
        "new_message": "Hola Alex"
    }

    response = client.post(
        "/api/v1/ai/alex-io",
        headers={"x-tenant-subdomain": "t1"},
        json=payload
    )

    assert response.status_code == 500
    assert "insuficientes" in response.json()["detail"].lower()

@pytest.mark.anyio
async def test_css_sanitization_xss():
    assert sanitize_css_property("#ffffff") == "#ffffff"
    assert sanitize_css_property("linear-gradient(to right, #000, #fff)") == "linear-gradient(to right, #000, #fff)"
    assert sanitize_css_property("8px") == "8px"
    assert sanitize_css_property("Outfit") == "Outfit"

    with pytest.raises(ValueError, match="no seguro detectado"):
        sanitize_css_property("url('javascript:alert(1)')")

    with pytest.raises(ValueError, match="no seguro detectado"):
        sanitize_css_property("expression(alert(1))")

    with pytest.raises(ValueError, match="no seguro detectado"):
        sanitize_css_property("<script>alert(1)</script>")

@pytest.mark.anyio
async def test_template_studio_success(client, session, monkeypatch):
    t1 = Tenant(name="Tenant 1", subdomain="t1", ai_credits=100)
    session.add(t1)
    session.commit()

    mock_theme = {
        "primary_color": "#112233",
        "secondary_color": "#445566",
        "mode": "dark",
        "background_gradient": "linear-gradient(to right, #112233, #000000)",
        "border_radius": "10px",
        "font_family": "Outfit"
    }

    mock_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(mock_theme)}]
                }
            }
        ]
    }

    async def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_response_data
        return mock_resp

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    response = client.post(
        "/api/v1/ai/template-studio",
        headers={"x-tenant-subdomain": "t1"},
        json={"prompt": "Quiero una estética cyberpunk", "page_name": "storefront_home"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["theme"]["primary_color"] == "#112233"

    db_tenant = session.get(Tenant, t1.id)
    assert db_tenant.ai_credits == 90

    config = session.exec(
        select(UIConfig).where(UIConfig.tenant_id == t1.id, UIConfig.page_name == "storefront_home")
    ).first()
    assert config is not None
    assert json.loads(config.theme_json)["primary_color"] == "#112233"

@pytest.mark.anyio
async def test_credits_management_endpoints(client, session):
    t1 = Tenant(name="Tenant 1", subdomain="t1", ai_credits=50, ai_tier="free")
    session.add(t1)
    session.commit()

    resp_get = client.get("/api/v1/ai/credits", headers={"x-tenant-subdomain": "t1"})
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert data_get["ai_credits"] == 50
    assert data_get["ai_tier"] == "free"

    resp_buy = client.post("/api/v1/ai/credits/buy?amount=150", headers={"x-tenant-subdomain": "t1"})
    assert resp_buy.status_code == 200
    data_buy = resp_buy.json()
    assert data_buy["ai_credits"] == 200

    db_tenant = session.get(Tenant, t1.id)
    assert db_tenant.ai_credits == 200
