import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
import json
import httpx
from unittest.mock import MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from main import app
from database.session import get_session
from database.models import Tenant, User, Product, Sale
from services.jwt_service import create_access_token
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
async def test_superadmin_dashboard_unauthorized(client, session):
    t2 = Tenant(name="Tenant 2", subdomain="t2")
    session.add(t2)
    session.commit()

    u2 = User(tenant_id=t2.id, username="cashier_user", password_hash="hash", role="cashier")
    session.add(u2)
    session.commit()

    token = create_access_token(u2.id, t2.id, u2.role)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/superadmin/dashboard", headers=headers)
    assert response.status_code == 403
    assert "superadmin required" in response.json()["detail"].lower()

@pytest.mark.anyio
async def test_superadmin_dashboard_success(client, session):
    t1 = Tenant(name="Super Tenant", subdomain="super")
    session.add(t1)
    session.commit()

    assert t1.id == 1

    u1 = User(tenant_id=t1.id, username="superadmin_user", password_hash="hash", role="admin")
    session.add(u1)
    session.commit()

    p1 = Product(tenant_id=t1.id, name="Test Product", barcode="abc", price=10.0)
    session.add(p1)
    session.commit()

    s1 = Sale(tenant_id=t1.id, total_amount=100.0, timestamp=datetime.utcnow())
    session.add(s1)
    session.commit()

    token = create_access_token(u1.id, t1.id, u1.role)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/superadmin/dashboard", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["tenants"]) == 1
    t_data = data["tenants"][0]
    assert t_data["tenant_id"] == 1
    assert t_data["metrics"]["products_count"] == 1
    assert t_data["metrics"]["sales_count"] == 1
    assert t_data["metrics"]["estimated_bandwidth_kb"] > 0

@pytest.mark.anyio
async def test_toggle_tenant_success(client, session):
    t1 = Tenant(name="Super Tenant", subdomain="super")
    t2 = Tenant(name="Tenant 2", subdomain="t2", is_active=True)
    session.add(t1)
    session.add(t2)
    session.commit()

    u1 = User(tenant_id=t1.id, username="superadmin_user", password_hash="hash", role="admin")
    session.add(u1)
    session.commit()

    token = create_access_token(u1.id, t1.id, u1.role)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(f"/api/v1/superadmin/tenants/{t2.id}/toggle", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False

    db_t2 = session.get(Tenant, t2.id)
    assert db_t2.is_active is False

    response_self = client.post(f"/api/v1/superadmin/tenants/1/toggle", headers=headers)
    assert response_self.status_code == 200
    assert response_self.json()["is_active"] is True

@pytest.mark.anyio
async def test_security_audit_logs(client, session, monkeypatch):
    t1 = Tenant(name="Super Tenant", subdomain="super", ai_credits=100)
    session.add(t1)
    session.commit()

    u1 = User(tenant_id=t1.id, username="superadmin_user", password_hash="hash", role="admin")
    session.add(u1)
    session.commit()

    token = create_access_token(u1.id, t1.id, u1.role)
    headers = {"Authorization": f"Bearer {token}"}

    mock_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "El reporte indica un posible ataque de fuerza bruta."}]
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
        "/api/v1/superadmin/security-audit",
        headers=headers,
        json={"audit_logs": []}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "fuerza bruta" in data["report"].lower()

    db_tenant = session.get(Tenant, t1.id)
    assert db_tenant.ai_credits == 90
