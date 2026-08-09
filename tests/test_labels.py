import os
os.environ["SECRET_KEY"] = "test-secret-key-12345"

import pytest
from sqlmodel import Session, SQLModel, create_engine
from database.models import Product, Tenant, Settings, User
from services.label_service import LabelService

from fastapi.testclient import TestClient
from main import app
from database.session import get_session

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_prepare_labels_data_with_quantities(session):
    tenant = Tenant(name="Test Tenant")
    session.add(tenant)
    session.commit()
    
    p1 = Product(tenant_id=tenant.id, name="Prod 1", barcode="779001", price=100.0, stock_quantity=10)
    p2 = Product(tenant_id=tenant.id, name="Prod 2", barcode="779002", price=200.0, stock_quantity=20)
    session.add(p1)
    session.add(p2)
    session.commit()
    
    # 2 copies of p1 and 1 copy of p2
    product_ids = [p1.id, p1.id, p2.id]
    labels_data = LabelService.prepare_labels_data(session, tenant.id, product_ids)
    
    assert len(labels_data) == 3
    assert labels_data[0]["name"] == "Prod 1"
    assert labels_data[1]["name"] == "Prod 1"
    assert labels_data[2]["name"] == "Prod 2"
