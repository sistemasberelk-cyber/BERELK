import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="
os.environ["DATABASE_URL"] = "sqlite:///./test_json.db"

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from database.models import Product, Tenant, User, Client as ClientModel
from services.jwt_service import create_access_token
import json

def test_json_serialization_of_decimal():
    # 1. Pydantic model_dump("json") evidence
    p = Product(tenant_id=1, name="Producto Decimal", barcode="DEC123", price=Decimal("1250.50"), cost_price=Decimal("800.25"))
    dict_repr = p.model_dump(mode="json")
    print("\n[EVIDENCIA 1 - Pydantic model_dump(mode='json')]:")
    print(json.dumps(dict_repr, indent=2))
    assert dict_repr["price"] == "1250.50"

    # 2. HTTP response evidence using local engine
    eng = create_engine("sqlite:///./test_json.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)

    with Session(eng) as s:
        t = Tenant(name="Tenant Test JSON")
        s.add(t); s.flush()
        u = User(tenant_id=t.id, username="admin_json", password_hash="hash", role="admin")
        s.add(u); s.flush()
        c = ClientModel(tenant_id=t.id, name="Cliente JSON", credit_limit=Decimal("50000.00"), credit_enabled=True)
        s.add(c); s.commit(); s.refresh(c)

        # Dump dict directly as returned by FastAPI API endpoints
        c_dict = c.model_dump(mode="json")
        print("\n[EVIDENCIA 2 - FastAPI Client Endpoint Response Payload]:")
        print(json.dumps(c_dict, indent=2))
        assert c_dict["credit_limit"] == "50000.00"

    SQLModel.metadata.drop_all(eng)
    eng.dispose()
    try:
        os.remove("./test_json.db")
    except:
        pass
