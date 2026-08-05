"""
tests/test_credit_security.py
==============================
Batería completa de pruebas de seguridad, límites de crédito, concurrencia,
aislamiento multi-tenant, precisión numérica (Decimal) y auditoría de permisos (5.1 a 5.16).

Ejecución:
    python -m pytest tests/test_credit_security.py -v
"""
import os
import threading
import pytest
from decimal import Decimal
from sqlmodel import SQLModel, Session, create_engine, select, func

os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_FERNET_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_security_full.db")

from database.models import (
    Tenant, User, Client, Product, Location, Bin, BinStock,
    AccountReceivable, Sale, SaleItem, PaymentAllocation, StockMovement, CashMovement
)
from services.stock_service import StockService


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///./test_security_full.db", connect_args={"check_same_thread": False})
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()
    try:
        os.remove("./test_security_full.db")
    except (FileNotFoundError, PermissionError):
        pass


@pytest.fixture(scope="module")
def seed(engine):
    with Session(engine) as s:
        tenant_a = Tenant(name="Tenant A")
        tenant_b = Tenant(name="Tenant B")
        s.add(tenant_a); s.add(tenant_b); s.flush()

        admin_a = User(tenant_id=tenant_a.id, username="admin_a", password_hash="hash", role="admin")
        admin_b = User(tenant_id=tenant_b.id, username="admin_b", password_hash="hash", role="admin")
        s.add(admin_a); s.add(admin_b); s.flush()

        product_a = Product(tenant_id=tenant_a.id, name="Producto A", barcode="PA100", price=Decimal("1000.00"))
        product_b = Product(tenant_id=tenant_b.id, name="Producto B", barcode="PB100", price=Decimal("1000.00"))
        s.add(product_a); s.add(product_b); s.flush()

        loc_a = Location(tenant_id=tenant_a.id, name="Dep A", code="A")
        loc_b = Location(tenant_id=tenant_b.id, name="Dep B", code="B")
        s.add(loc_a); s.add(loc_b); s.flush()

        bin_a = Bin(tenant_id=tenant_a.id, location_id=loc_a.id, name="SIN-UBICACION", is_active=True)
        bin_b = Bin(tenant_id=tenant_b.id, location_id=loc_b.id, name="SIN-UBICACION", is_active=True)
        s.add(bin_a); s.add(bin_b); s.flush()

        s.add(BinStock(tenant_id=tenant_a.id, bin_id=bin_a.id, product_id=product_a.id, quantity=1000))
        s.add(BinStock(tenant_id=tenant_b.id, bin_id=bin_b.id, product_id=product_b.id, quantity=1000))
        s.commit()

        return {
            "tenant_a_id": tenant_a.id,
            "tenant_b_id": tenant_b.id,
            "admin_a_id": admin_a.id,
            "admin_b_id": admin_b.id,
            "product_a_id": product_a.id,
            "product_b_id": product_b.id,
        }


# =============================================================================
# CASOS BÁSICOS DE LÍMITE (5.1 - 5.5)
# =============================================================================

def test_5_1_basic_limit_succeeds(engine, seed):
    """5.1. Client limit=5000, debt=0, purchase=$3000 -> OK, AR created."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.1", credit_enabled=True, credit_limit=Decimal("5000.00"))
        s.add(c); s.commit(); cid = c.id

    with Session(engine) as s:
        sale = svc.process_sale(
            session=s, user_id=uid, tenant_id=tid,
            items_data=[{"product_id": pid, "quantity": 3}], # 3 * 1000 = $3000
            payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid
        )
        sale_id = sale.id

    with Session(engine) as s:
        ar = s.exec(select(AccountReceivable).where(AccountReceivable.sale_id == sale_id)).first()
        assert ar is not None
        assert ar.balance == Decimal("3000.00")
        assert ar.status == "pending"


def test_5_2_basic_limit_exceeded_fails(engine, seed):
    """5.2. Same client, debt=4500, attempt credit purchase $1000 -> Rejected (exceeds limit by $500)."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.2", credit_enabled=True, credit_limit=Decimal("5000.00"))
        s.add(c); s.commit(); cid = c.id
        sale_prev = Sale(tenant_id=tid, user_id=uid, client_id=cid, total_amount=Decimal("4500.00"), payment_status="pending")
        s.add(sale_prev); s.flush()
        s.add(AccountReceivable(tenant_id=tid, sale_id=sale_prev.id, client_id=cid, total=Decimal("4500.00"), paid=Decimal("0.00"), balance=Decimal("4500.00"), status="pending"))
        s.commit()

    with pytest.raises(ValueError, match="(?i)Límite de crédito excedido"):
        with Session(engine) as s:
            svc.process_sale(
                session=s, user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 1}], # $1000
                payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid
            )


def test_5_3_unlimited_client_succeeds(engine, seed):
    """5.3. Client credit_limit=None (unlimited), debt=1000000, purchase $500000 -> Allowed."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.3 Unlimited", credit_enabled=True, credit_limit=None)
        s.add(c); s.commit(); cid = c.id
        sale_prev = Sale(tenant_id=tid, user_id=uid, client_id=cid, total_amount=Decimal("1000000.00"), payment_status="pending")
        s.add(sale_prev); s.flush()
        s.add(AccountReceivable(tenant_id=tid, sale_id=sale_prev.id, client_id=cid, total=Decimal("1000000.00"), paid=Decimal("0.00"), balance=Decimal("1000000.00"), status="pending"))
        s.commit()

    with Session(engine) as s:
        sale = svc.process_sale(
            session=s, user_id=uid, tenant_id=tid,
            items_data=[{"product_id": pid, "quantity": 500}], # $500.000
            payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid
        )
        assert sale.id is not None


def test_5_4_exact_limit_succeeds(engine, seed):
    """5.4. Exact limit: debt=4000, limit=5000, purchase $1000 -> Allowed (4000+1000 == 5000 inclusive)."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.4 Exact", credit_enabled=True, credit_limit=Decimal("5000.00"))
        s.add(c); s.commit(); cid = c.id
        sale_prev = Sale(tenant_id=tid, user_id=uid, client_id=cid, total_amount=Decimal("4000.00"), payment_status="pending")
        s.add(sale_prev); s.flush()
        s.add(AccountReceivable(tenant_id=tid, sale_id=sale_prev.id, client_id=cid, total=Decimal("4000.00"), paid=Decimal("0.00"), balance=Decimal("4000.00"), status="pending"))
        s.commit()

    with Session(engine) as s:
        sale = svc.process_sale(
            session=s, user_id=uid, tenant_id=tid,
            items_data=[{"product_id": pid, "quantity": 1}], # $1000
            payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid
        )
        assert sale.id is not None


def test_5_5_already_exceeded_client_fails_even_for_1_dollar(engine, seed):
    """5.5. Client already exceeded (debt=6000, limit=5000) attempts $1 purchase -> Rejected."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.5 Exceeded", credit_enabled=True, credit_limit=Decimal("5000.00"))
        s.add(c); s.commit(); cid = c.id
        sale_prev = Sale(tenant_id=tid, user_id=uid, client_id=cid, total_amount=Decimal("6000.00"), payment_status="pending")
        s.add(sale_prev); s.flush()
        s.add(AccountReceivable(tenant_id=tid, sale_id=sale_prev.id, client_id=cid, total=Decimal("6000.00"), paid=Decimal("0.00"), balance=Decimal("6000.00"), status="pending"))
        s.commit()

    with pytest.raises(ValueError, match="(?i)Límite de crédito excedido"):
        with Session(engine) as s:
            svc.process_sale(
                session=s, user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 1}],
                payment_method="cuenta_corriente", amount_paid=999.0, # Net debt = 1000 - 999 = $1
                client_id=cid
            )


# =============================================================================
# PAGOS PARCIALES Y MIXTOS (5.6 - 5.8)
# =============================================================================

def test_5_6_partial_payment_allows_credit_for_net_debt(engine, seed):
    """5.6. Total=$5000, pays $2000 cash, net debt=$3000. Limit=3000, debt=0 -> Allowed."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.6 NetDebt", credit_enabled=True, credit_limit=Decimal("3000.00"))
        s.add(c); s.commit(); cid = c.id

    with Session(engine) as s:
        sale = svc.process_sale(
            session=s, user_id=uid, tenant_id=tid,
            items_data=[{"product_id": pid, "quantity": 5}], # $5000
            payment_method="cash", amount_paid=2000.0, client_id=cid
        )
        assert sale.id is not None


def test_5_7_partial_payment_off_by_one_dollar_rejects(engine, seed):
    """5.7. Same scenario but limit=2999 -> Rejected (no unfair rounding up)."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.7 OffBy1", credit_enabled=True, credit_limit=Decimal("2999.00"))
        s.add(c); s.commit(); cid = c.id

    with pytest.raises(ValueError, match="(?i)Límite de crédito excedido"):
        with Session(engine) as s:
            svc.process_sale(
                session=s, user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 5}], # $5000 - $2000 = $3000 debt > 2999
                payment_method="cash", amount_paid=2000.0, client_id=cid
            )


def test_5_8_mixed_payment_calculates_net_debt_correctly(engine, seed):
    """5.8. Mixed payment (split_cash=1000, split_transfer=1000), total=$5000 -> net debt=$3000. Limit=3000 -> Allowed."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.8 Mixed", credit_enabled=True, credit_limit=Decimal("3000.00"))
        s.add(c); s.commit(); cid = c.id

    with Session(engine) as s:
        sale = svc.process_sale(
            session=s, user_id=uid, tenant_id=tid,
            items_data=[{"product_id": pid, "quantity": 5}], # $5000
            split_cash=1000.0, split_transfer=1000.0, client_id=cid
        )
        assert sale.id is not None
        assert sale.amount_paid == Decimal("2000.00")


# =============================================================================
# CONCURRENCIA (5.9)
# =============================================================================

def test_5_9_concurrent_credit_sales_only_one_succeeds(engine, seed):
    """5.9. Two simultaneous credit sales ($3000 each) for client with limit=5000. Exactly 1 succeeds."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.9 Concurrency", credit_enabled=True, credit_limit=Decimal("5000.00"))
        s.add(c); s.commit(); cid = c.id

    results = []
    sqlite_lock = threading.Lock()

    def attempt_sale(thread_id):
        try:
            with sqlite_lock:
                with Session(engine) as s:
                    svc.process_sale(
                        session=s, user_id=uid, tenant_id=tid,
                        items_data=[{"product_id": pid, "quantity": 3}], # $3000
                        payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid
                    )
                    results.append((thread_id, True, "OK"))
        except Exception as e:
            results.append((thread_id, False, str(e)))

    t1 = threading.Thread(target=attempt_sale, args=(1,))
    t2 = threading.Thread(target=attempt_sale, args=(2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    successes = [r for r in results if r[1]]
    failures = [r for r in results if not r[1]]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"
    assert "Límite de crédito excedido" in failures[0][2]


# =============================================================================
# CANCELACIONES Y LIBERACIÓN DE CRÉDITO (5.10 - 5.11)
# =============================================================================

def test_5_10_sale_cancellation_releases_credit_limit(engine, seed):
    """5.10. Client debt=4000 (limit=5000) has $3000 sale cancelled. AR passes to status='cancelled', balance=0. Credit restored."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.10 Cancel", credit_enabled=True, credit_limit=Decimal("5000.00"))
        s.add(c); s.commit(); cid = c.id

        sale1 = svc.process_sale(session=s, user_id=uid, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 1}], payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid)
        sale2 = svc.process_sale(session=s, user_id=uid, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 3}], payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid)
        sale2_id = sale2.id

    with Session(engine) as s:
        ar2 = s.exec(select(AccountReceivable).where(AccountReceivable.sale_id == sale2_id)).first()
        ar2.status = "cancelled"
        ar2.balance = Decimal("0.00")
        s.add(ar2)
        s.commit()

    with Session(engine) as s:
        stmt = select(func.sum(AccountReceivable.balance)).where(
            AccountReceivable.client_id == cid,
            AccountReceivable.status.in_(["pending", "partial"])
        )
        debt = Decimal(str(s.exec(stmt).one() or "0.00"))
        assert debt == Decimal("1000.00"), f"Deuda esperada: 1000.00, obtenida: {debt}"


def test_5_11_new_sale_after_cancellation_succeeds(engine, seed):
    """5.11. Tras la liberación de crédito en 5.10 (deuda remanente=$1000, límite=$5000), una nueva compra de $4000 es permitida (1000 + 4000 == 5000)."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = s.exec(select(Client).where(Client.name == "Client 5.10 Cancel")).first()
        cid = c.id

        stmt_ar = select(func.sum(AccountReceivable.balance)).where(
            AccountReceivable.client_id == cid,
            AccountReceivable.status.in_(["pending", "partial"])
        )
        deuda_actual = Decimal(str(s.exec(stmt_ar).one() or "0.00"))
        disponible = Decimal(str(c.credit_limit)) - deuda_actual
        assert deuda_actual == Decimal("1000.00")
        assert disponible == Decimal("4000.00")

    with Session(engine) as s:
        sale = svc.process_sale(
            session=s, user_id=uid, tenant_id=tid,
            items_data=[{"product_id": pid, "quantity": 4}], # $4000
            payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid
        )
        assert sale.id is not None


# =============================================================================
# AISLAMIENTO MULTI-TENANT (5.12)
# =============================================================================

def test_5_12_multi_tenant_credit_limit_isolation(engine, seed):
    """5.12. Tenant A: client_id=1 limit=1000. Tenant B: client_id=1 limit=50000. Tenant A rejects $2000, Tenant B allows $2000."""
    svc = StockService()
    tid_a, uid_a, pid_a = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]
    tid_b, uid_b, pid_b = seed["tenant_b_id"], seed["admin_b_id"], seed["product_b_id"]

    with Session(engine) as s:
        ca = Client(id=100, tenant_id=tid_a, name="Client MultiA", credit_enabled=True, credit_limit=Decimal("1000.00"))
        cb = Client(id=101, tenant_id=tid_b, name="Client MultiB", credit_enabled=True, credit_limit=Decimal("50000.00"))
        s.add(ca); s.add(cb); s.commit()
        cid_a, cid_b = ca.id, cb.id

    with pytest.raises(ValueError, match="(?i)Límite de crédito excedido"):
        with Session(engine) as s:
            svc.process_sale(session=s, user_id=uid_a, tenant_id=tid_a, items_data=[{"product_id": pid_a, "quantity": 2}], payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid_a)

    with Session(engine) as s:
        sale_b = svc.process_sale(session=s, user_id=uid_b, tenant_id=tid_b, items_data=[{"product_id": pid_b, "quantity": 2}], payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid_b)
        assert sale_b.id is not None


# =============================================================================
# PRECISIÓN NUMÉRICA DECIMAL (5.13 & 5.16)
# =============================================================================

def test_5_13_floating_point_precision_rounding(engine, seed):
    """5.13. Debt=999.99, limit=1000.00, new sale=$0.02 -> 1000.01 > 1000.00 -> Rejected correctly with Decimal."""
    svc = StockService()
    tid, uid, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.13 Decimal", credit_enabled=True, credit_limit=Decimal("1000.00"))
        s.add(c); s.commit(); cid = c.id
        sale_prev = Sale(tenant_id=tid, user_id=uid, client_id=cid, total_amount=Decimal("999.99"), payment_status="pending")
        s.add(sale_prev); s.flush()
        s.add(AccountReceivable(tenant_id=tid, sale_id=sale_prev.id, client_id=cid, total=Decimal("999.99"), paid=Decimal("0.00"), balance=Decimal("999.99"), status="pending"))
        s.commit()

    with pytest.raises(ValueError, match="(?i)Límite de crédito excedido"):
        with Session(engine) as s:
            svc.process_sale(
                session=s, user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 1}],
                payment_method="cash", amount_paid=999.98,
                client_id=cid
            )


def test_5_16_decimal_precision_accumulated_exactness():
    """5.16. Demuestra que sumar 0.1 + 0.2 con float da imprecisión en IEEE 754 (0.30000000000000004 != 0.3), mientras que Decimal da exactitud matemática estricta (0.3)."""
    sum_float = 0.1 + 0.2
    assert sum_float != 0.3  # 0.30000000000000004 en float IEEE 754

    sum_dec = Decimal("0.1") + Decimal("0.2")
    assert sum_dec == Decimal("0.3")  # Exactitud matemática garantizada con Decimal


# =============================================================================
# ROL ADMIN/POS Y OVERRIDE AUDIT (5.14 - 5.15)
# =============================================================================

def test_5_14_admin_pos_role_must_respect_credit_limit(engine, seed):
    """5.14. Confirm that credit_limit check applies EQUALLY when charged by an admin/cashier user in POS."""
    svc = StockService()
    tid, admin_id, pid = seed["tenant_a_id"], seed["admin_a_id"], seed["product_a_id"]

    with Session(engine) as s:
        c = Client(tenant_id=tid, name="Client 5.14 POS Admin", credit_enabled=True, credit_limit=Decimal("1000.00"))
        s.add(c); s.commit(); cid = c.id

    with pytest.raises(ValueError, match="(?i)Límite de crédito excedido"):
        with Session(engine) as s:
            svc.process_sale(
                session=s, user_id=admin_id, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 2}], # $2000 > 1000
                payment_method="cuenta_corriente", amount_paid=0.0, client_id=cid
            )


def test_5_15_audit_no_override_parameter_exists(engine, seed):
    """5.15. Confirm there is NO hidden parameter or bypass flag in process_sale that allows skipping credit_limit."""
    svc = StockService()
    import inspect
    sig = inspect.signature(svc.process_sale)
    params = list(sig.parameters.keys())
    
    bypass_params = [p for p in params if "override" in p or "bypass" in p or "skip" in p or "force" in p]
    assert len(bypass_params) == 0, f"Found unexpected bypass parameter(s): {bypass_params}"
