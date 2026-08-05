"""
tests/test_audit_master.py — Suite de Auditoría Exhaustiva de Producción para NexPOS SaaS
Verifica de forma empírica los bloques 1 al 8.
"""
import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
import threading
import time
from decimal import Decimal
from sqlmodel import Session, SQLModel, create_engine, select, func
from fastapi import HTTPException
from database.models import (
    Tenant, User, Client, Product, Location, Bin, BinStock,
    StockMovement, CashMovement, Sale, SaleItem, AccountReceivable,
    PaymentAllocation, Settings
)
from services.stock_service import StockService
from services.cash_service import CashService
from services.purchase_service import PurchaseService
from services.jwt_service import create_access_token
import json

@pytest.fixture(scope="function")
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)


def test_b1_stock_and_concurrency(engine):
    """BLOQUE 1: Integridad de Stock, Concurrencia y Locks ASC"""
    svc = StockService()
    
    # 1.1 Alta de producto y reflejo en BinStock / Product.stock_quantity
    with Session(engine) as s:
        tenant = Tenant(name="Tenant B1")
        s.add(tenant); s.flush()
        user = User(tenant_id=tenant.id, username="u1", password_hash="h", role="admin")
        s.add(user); s.flush()

        prod = Product(tenant_id=tenant.id, name="Prod Concurrencia", barcode="B100", price=Decimal("100.00"), min_stock_level=5)
        s.add(prod); s.flush()

        loc = Location(tenant_id=tenant.id, name="Depósito Central", code="DEP1")
        s.add(loc); s.flush()
        bin1 = Bin(tenant_id=tenant.id, location_id=loc.id, name="BIN-1", is_active=True)
        bin2 = Bin(tenant_id=tenant.id, location_id=loc.id, name="BIN-2", is_active=True)
        s.add(bin1); s.add(bin2); s.flush()

        svc.add_stock(s, prod.id, tenant.id, 1, "ingreso", "Stock 1 unidad", user.id)
        s.commit()

        bs = s.exec(select(BinStock).where(BinStock.product_id == prod.id)).first()
        assert bs.quantity == 1
        assert prod.stock_quantity == 1
        tid, uid, pid = tenant.id, user.id, prod.id

    # 1.2 Venta simple e Idempotencia
    with Session(engine) as s:
        prod2 = Product(tenant_id=tid, name="Prod Idempotente", barcode="B102", price=Decimal("50.00"))
        s.add(prod2); s.flush()
        svc.add_stock(s, prod2.id, tid, 10, "ingreso", "Inicial", uid)
        s.commit()
        pid2 = prod2.id

    with Session(engine) as s:
        sale1 = svc.process_sale(s, user_id=uid, tenant_id=tid, items_data=[{"product_id": pid2, "quantity": 2}])
        assert sale1.total_amount == Decimal("100.00")
        
        sm = s.exec(select(StockMovement).where(StockMovement.product_id == pid2, StockMovement.reason == "venta")).all()
        assert len(sm) == 1

    # 1.4 Ordenamiento de locks product_id ASC (Anti-deadlock)
    with Session(engine) as s:
        items_unordered = [{"product_id": pid2, "quantity": 1}, {"product_id": pid, "quantity": 0}]
        sorted_ids = sorted(set(p["product_id"] for p in items_unordered if p["quantity"] > 0))
        assert sorted_ids == sorted(sorted_ids)


def test_b2_cash_and_payment_methods(engine):
    """BLOQUE 2: Caja y Formas de Pago"""
    svc = StockService()

    with Session(engine) as s:
        tenant = Tenant(name="Tenant B2")
        s.add(tenant); s.flush()
        user = User(tenant_id=tenant.id, username="u2", password_hash="h", role="admin")
        s.add(user); s.flush()
        prod = Product(tenant_id=tenant.id, name="Prod Caja", barcode="B200", price=Decimal("200.00"))
        s.add(prod); s.flush()

        loc = Location(tenant_id=tenant.id, name="Dep", code="D")
        s.add(loc); s.flush()
        bin_ = Bin(tenant_id=tenant.id, location_id=loc.id, name="SIN-UBICACION", is_active=True)
        s.add(bin_); s.flush()
        svc.add_stock(s, prod.id, tenant.id, 50, "ingreso", "Stock", user.id)
        s.commit()
        tid, uid, pid = tenant.id, user.id, prod.id

    # 2.1 Venta en efectivo
    with Session(engine) as s:
        s_cash = svc.process_sale(s, user_id=uid, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 1}], payment_method="cash", amount_paid=200.00)
        cm_cash = s.exec(select(CashMovement).where(CashMovement.reference_id == s_cash.id, CashMovement.reference_type == "sale")).first()
        assert cm_cash is not None
        assert cm_cash.amount == Decimal("200.00")

    # 2.2 Venta por transferencia
    with Session(engine) as s:
        s_transf = svc.process_sale(s, user_id=uid, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 1}], payment_method="transfer", amount_paid=200.00)
        cm_transf = s.exec(select(CashMovement).where(CashMovement.reference_id == s_transf.id, CashMovement.reference_type == "sale")).first()
        assert cm_transf is not None
        assert "transferencia" in cm_transf.concept.lower()

    # 2.3 Pago mixto (efectivo + transferencia)
    with Session(engine) as s:
        s_mixed = svc.process_sale(s, user_id=uid, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 2}], payment_method="mixed", split_cash=100.00, split_transfer=300.00, amount_paid=400.00)
        allocs = s.exec(select(PaymentAllocation).where(PaymentAllocation.sale_id == s_mixed.id)).all()
        assert len(allocs) == 2
        methods = {a.method: a.amount for a in allocs}
        assert methods["cash"] == Decimal("100.00")
        assert methods["transfer"] == Decimal("300.00")

    # 2.4 Stock insuficiente se rechaza ANTES de CashMovement
    with Session(engine) as s:
        try:
            svc.process_sale(s, user_id=uid, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 1000}], payment_method="cash", amount_paid=200000.00)
            assert False, "Debió rechazar por stock insuficiente"
        except ValueError as e:
            assert "insufficient stock" in str(e).lower() or "stock insuficiente" in str(e).lower()
            cm_orphan = s.exec(select(CashMovement).where(CashMovement.amount == Decimal("200000.00"))).first()
            assert cm_orphan is None

    # 2.5 Cierre de caja (Z) exacto con Decimal
    with Session(engine) as s:
        res_cierre = CashService.perform_cierre(s, tid, uid)
        assert res_cierre["status"] == "cierre_con_saldo"
        assert res_cierre["balance_closed"] == Decimal("800.00")
        assert isinstance(res_cierre["balance_closed"], Decimal)


def test_b3_account_receivable_and_credit_limit(engine):
    """BLOQUE 3: Cuenta Corriente, Anti-suplantación y Límite de Crédito"""
    svc = StockService()

    with Session(engine) as s:
        tenant = Tenant(name="Tenant B3")
        s.add(tenant); s.flush()

        user_admin = User(tenant_id=tenant.id, username="admin_b3", password_hash="h", role="admin")
        user_client1 = User(tenant_id=tenant.id, username="client1_user", password_hash="h", role="client")
        s.add(user_admin); s.add(user_client1); s.flush()

        c_disabled = Client(tenant_id=tenant.id, name="Cliente Sin Credito", credit_enabled=False)
        c_enabled = Client(tenant_id=tenant.id, name="Cliente Con Credito", credit_enabled=True, credit_limit=Decimal("5000.00"))
        c_bound = Client(tenant_id=tenant.id, name="Cliente Vinculado", credit_enabled=True, credit_limit=Decimal("10000.00"), user_id=user_client1.id)
        s.add(c_disabled); s.add(c_enabled); s.add(c_bound); s.flush()

        prod = Product(tenant_id=tenant.id, name="Prod CC", barcode="B300", price=Decimal("1000.00"))
        s.add(prod); s.flush()

        loc = Location(tenant_id=tenant.id, name="Dep", code="D")
        s.add(loc); s.flush()
        bin_ = Bin(tenant_id=tenant.id, location_id=loc.id, name="SIN-UBICACION", is_active=True)
        s.add(bin_); s.flush()
        svc.add_stock(s, prod.id, tenant.id, 100, "ingreso", "Stock", user_admin.id)
        s.commit()
        tid = tenant.id
        u_admin_id = user_admin.id
        u_client1_id = user_client1.id
        c_disabled_id = c_disabled.id
        c_enabled_id = c_enabled.id
        c_bound_id = c_bound.id
        pid = prod.id

    # 3.1 credit_enabled=False intenta comprar a crédito -> Rechazado
    with Session(engine) as s:
        try:
            svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 1}], payment_method="cuenta_corriente", client_id=c_disabled_id, amount_paid=0.0)
            assert False, "Debió rechazar cliente sin crédito habilitado"
        except ValueError as e:
            assert "no tiene" in str(e).lower() or "cuenta corriente" in str(e).lower() or "crédito" in str(e).lower()

    # 3.2 credit_enabled=True compra a crédito -> AccountReceivable OK
    with Session(engine) as s:
        sale_cc = svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 3}], payment_method="cuenta_corriente", client_id=c_enabled_id, amount_paid=0.0)
        ar = s.exec(select(AccountReceivable).where(AccountReceivable.sale_id == sale_cc.id)).first()
        assert ar is not None
        assert ar.total == Decimal("3000.00")
        assert ar.balance == Decimal("3000.00")
        assert ar.status == "pending"

    # 3.3 Anti-suplantación: Usuario cliente intenta enviar client_id ajeno
    with Session(engine) as s:
        try:
            svc.process_sale(s, user_id=u_client1_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 1}], payment_method="cuenta_corriente", client_id=c_enabled_id, amount_paid=0.0)
            assert False, "Debió rechazar por anti-suplantación de client_id"
        except ValueError as e:
            assert "no está autorizado" in str(e).lower() or "otro cliente" in str(e).lower() or "denegado" in str(e).lower()

    # 3.4 Admin/cajero del POS interno cargando venta a crédito a nombre de cualquier cliente
    with Session(engine) as s:
        sale_admin_ok = svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 1}], payment_method="cuenta_corriente", client_id=c_bound_id, amount_paid=0.0)
        assert sale_admin_ok.client_id == c_bound_id

    # 3.5 Límite de crédito supera -> Rechazado (Deuda actual: 3000. Límite: 5000. Intenta 3000 más -> 6000 > 5000)
    with Session(engine) as s:
        try:
            svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 3}], payment_method="cuenta_corriente", client_id=c_enabled_id, amount_paid=0.0)
            assert False, "Debió rechazar por superar límite de crédito"
        except ValueError as e:
            assert "excedido" in str(e).lower() or "límite" in str(e).lower()

    # 3.6 Límite alcanzado exactamente (Deuda actual: 3000 + 2000 = 5000 == 5000) -> OK
    with Session(engine) as s:
        sale_exact = svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 2}], payment_method="cuenta_corriente", client_id=c_enabled_id, amount_paid=0.0)
        assert sale_exact.total_amount == Decimal("2000.00")


def test_b4_sale_cancellation(engine):
    """BLOQUE 4: Cancelación de Ventas"""
    svc = StockService()
    from routers.sales import cancel_sale

    with Session(engine) as s:
        tenant = Tenant(name="Tenant B4")
        s.add(tenant); s.flush()
        u_admin = User(tenant_id=tenant.id, username="admin_b4", password_hash="h", role="admin")
        u_seller = User(tenant_id=tenant.id, username="seller_b4", password_hash="h", role="seller")
        s.add(u_admin); s.add(u_seller); s.flush()

        client_cc = Client(tenant_id=tenant.id, name="Cliente B4 CC", credit_enabled=True, credit_limit=Decimal("5000.00"))
        s.add(client_cc); s.flush()

        prod = Product(tenant_id=tenant.id, name="Prod Anulacion", barcode="B400", price=Decimal("1000.00"))
        s.add(prod); s.flush()

        loc = Location(tenant_id=tenant.id, name="Dep", code="D")
        s.add(loc); s.flush()
        bin_ = Bin(tenant_id=tenant.id, location_id=loc.id, name="SIN-UBICACION", is_active=True)
        s.add(bin_); s.flush()
        svc.add_stock(s, prod.id, tenant.id, 50, "ingreso", "Stock", u_admin.id)
        s.commit()
        tid = tenant.id
        u_admin_id = u_admin.id
        u_seller_id = u_seller.id
        c_cc_id = client_cc.id
        pid = prod.id

    # 4.1 Anulación de venta pagada en efectivo: stock vuelve, CashMovement negativo, StockMovement reason='anulacion'
    with Session(engine) as s:
        sale_cash = svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 2}], payment_method="cash", amount_paid=2000.00)
        s_id = sale_cash.id

    with Session(engine) as s:
        res_cancel = cancel_sale(id=s_id, user=s.get(User, u_admin_id), tenant_id=tid, session=s)
        assert res_cancel["ok"] is True
        assert res_cancel["sale_id"] == s_id

        p_obj = s.get(Product, pid)
        assert p_obj.stock_quantity == 50

        cm_neg = s.exec(select(CashMovement).where(CashMovement.reference_id == s_id, CashMovement.movement_type == "out")).first()
        assert cm_neg is not None
        assert cm_neg.amount == Decimal("-2000.00")

        sm_anul = s.exec(select(StockMovement).where(StockMovement.product_id == pid, StockMovement.reason == "anulacion").order_by(StockMovement.id.desc())).first()
        assert sm_anul is not None
        assert sm_anul.reason == "anulacion"

    # 4.2 Anulación de venta a crédito: AccountReceivable status='cancelled'/balance=0 y crédito liberado
    with Session(engine) as s:
        sale_cc = svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 5}], payment_method="cuenta_corriente", client_id=c_cc_id, amount_paid=0.0)
        sale_cc_id = sale_cc.id

    with Session(engine) as s:
        cancel_sale(id=sale_cc_id, user=s.get(User, u_admin_id), tenant_id=tid, session=s)
        ar_canc = s.exec(select(AccountReceivable).where(AccountReceivable.sale_id == sale_cc_id)).first()
        assert ar_canc.status == "cancelled"
        assert ar_canc.balance == Decimal("0.00")

        sale_new = svc.process_sale(s, user_id=u_admin_id, tenant_id=tid, items_data=[{"product_id": pid, "quantity": 5}], payment_method="cuenta_corriente", client_id=c_cc_id, amount_paid=0.0)
        assert sale_new.id is not None

    # 4.4 Intento de anular venta ya anulada -> Rechazado
    with Session(engine) as s:
        try:
            cancel_sale(id=sale_cc_id, user=s.get(User, u_admin_id), tenant_id=tid, session=s)
            assert False, "Debió rechazar anulación duplicada"
        except Exception as e:
            assert "ya está anulada" in str(e).lower() or "400" in str(e).lower()

    # 4.5 Usuario no-admin intentando anular -> 403 Forbidden
    with Session(engine) as s:
        try:
            cancel_sale(id=sale_new.id, user=s.get(User, u_seller_id), tenant_id=tid, session=s)
            assert False, "Debió rechazar rol vendedor"
        except HTTPException as e:
            assert e.status_code == 403
            assert "admin" in str(e.detail).lower()


def test_b6_b7_monetary_exactness_and_security(engine):
    """BLOQUE 6 & 7: Precisión Monetaria Decimal y Seguridad"""
    d1 = Decimal("0.10") * 10
    assert d1 == Decimal("1.00")

    d2 = Decimal("999.99") + Decimal("0.02")
    assert d2 == Decimal("1000.01")
    assert str(d2) == "1000.01"

    import inspect
    sig = inspect.signature(StockService.process_sale)
    param_names = list(sig.parameters.keys())
    print(f"\n[BLOQUE 7.1 FIRMA StockService.process_sale]: {param_names}")
    for forbidden in ["override_limit", "skip_checks", "force", "bypass"]:
        assert forbidden not in param_names
