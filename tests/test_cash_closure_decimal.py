"""tests/test_cash_closure_decimal.py — Test de Cierre de Caja sobre columnas Decimal"""
import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="
os.environ["DATABASE_URL"] = "sqlite:///./test_cash_decimal.db"

from datetime import date
import pytest
from decimal import Decimal
from sqlmodel import Session, SQLModel, create_engine, select
from database.models import Tenant, User, Client, Product, Location, Bin, BinStock, CashMovement, Sale, AccountReceivable
from services.stock_service import StockService
from services.cash_service import CashService

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///./test_cash_decimal.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()
    try:
        os.remove("./test_cash_decimal.db")
    except:
        pass

def test_cash_closure_decimal_execution(engine):
    """Ejecuta un cierre de caja completo sobre columnas migradas a Decimal."""
    svc = StockService()

    with Session(engine) as s:
        tenant = Tenant(name="Tenant Cash Closure")
        s.add(tenant); s.flush()

        user = User(tenant_id=tenant.id, username="cash_admin", password_hash="hash", role="admin")
        s.add(user); s.flush()

        prod = Product(tenant_id=tenant.id, name="Prod Cierre", barcode="C100", price=Decimal("1500.50"), cost_price=Decimal("700.25"))
        s.add(prod); s.flush()

        loc = Location(tenant_id=tenant.id, name="Dep Cierre", code="C")
        s.add(loc); s.flush()
        bin_ = Bin(tenant_id=tenant.id, location_id=loc.id, name="SIN-UBICACION", is_active=True)
        s.add(bin_); s.flush()
        s.add(BinStock(tenant_id=tenant.id, bin_id=bin_.id, product_id=prod.id, quantity=50))
        s.commit()
        tid, uid, pid = tenant.id, user.id, prod.id

    # 1. Registrar venta en efectivo por $1500.50
    with Session(engine) as s:
        sale = svc.process_sale(
            session=s, user_id=uid, tenant_id=tid,
            items_data=[{"product_id": pid, "quantity": 1}],
            payment_method="cash", amount_paid=1500.50
        )
        assert sale.total_amount == Decimal("1500.50")
        assert sale.amount_paid == Decimal("1500.50")

    # 2. Calcular balance previo al cierre
    with Session(engine) as s:
        bal_before = CashService.calculate_daily_balance(s, tid, date.today())
        print(f"\n[BALANCE PRE-CIERRE] Total In: {bal_before['total_in']} | Total Out: {bal_before['total_out']} | Balance: {bal_before['balance']}")
        assert bal_before["balance"] == Decimal("1500.50")
        assert isinstance(bal_before["balance"], Decimal)

    # 3. Ejecutar cierre de caja
    with Session(engine) as s:
        res = CashService.perform_cierre(s, tid, uid)
        print(f"[RESULTADO DE CIERRE DE CAJA]: {res}")
        assert res["status"] == "cierre_con_saldo"
        assert res["balance_closed"] == Decimal("1500.50")
        assert isinstance(res["balance_closed"], Decimal)

    # 4. Verificar que se creó el CashMovement de retiro y que el balance post-cierre es Decimal("0.00")
    with Session(engine) as s:
        cm_close = s.exec(
            select(CashMovement)
            .where(CashMovement.tenant_id == tid, CashMovement.concept.like("CIERRE_DE_CAJA%"))
        ).first()
        assert cm_close is not None
        assert cm_close.amount == Decimal("1500.50")
        assert isinstance(cm_close.amount, Decimal)

        bal_after = CashService.calculate_daily_balance(s, tid, date.today())
        print(f"[BALANCE POST-CIERRE] Balance Remanente: {bal_after['balance']}")
        assert bal_after["balance"] == Decimal("0.00")
        assert isinstance(bal_after["balance"], Decimal)
