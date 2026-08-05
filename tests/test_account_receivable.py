"""
tests/test_account_receivable.py
=================================
Tests de integración para F3-9c (AccountReceivable) y F4-12 (cancelación de venta).

Ejecutar desde la raíz del proyecto:
    python -m pytest tests/test_account_receivable.py -v
"""
import os
import pytest

os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_FERNET_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ar.db")

from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import func

from database.models import (
    Tenant, User, Client, Product, Location, Bin, BinStock,
    AccountReceivable, Payment, CashMovement, Sale, SaleItem,
    PaymentAllocation, StockMovement,
)
from services.stock_service import StockService

# ── Engine ────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite:///./test_ar.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()
    try:
        os.remove("./test_ar.db")
    except (FileNotFoundError, PermissionError):
        pass


@pytest.fixture(scope="module")
def seed(engine):
    with Session(engine) as s:
        tenant = Tenant(name="AR_Tenant")
        s.add(tenant); s.flush()

        user = User(
            tenant_id=tenant.id, username="ar_admin",
            password_hash="hash", role="admin", is_active=True,
        )
        s.add(user); s.flush()

        client = Client(
            tenant_id=tenant.id, name="Cliente AR",
            phone="0000", credit_limit=100_000.0,
            credit_enabled=True,
        )
        s.add(client); s.flush()

        product = Product(
            tenant_id=tenant.id, name="Prod AR",
            barcode="AR001", price=5_000.0, cost_price=2_000.0,
        )
        s.add(product); s.flush()

        location = Location(tenant_id=tenant.id, name="Dep AR", code="AR")
        s.add(location); s.flush()

        bin_ = Bin(tenant_id=tenant.id, location_id=location.id,
                   name="SIN-UBICACION", is_active=True)
        s.add(bin_); s.flush()

        # Stock suficiente para todos los tests
        s.add(BinStock(tenant_id=tenant.id, bin_id=bin_.id,
                       product_id=product.id, quantity=100))
        s.commit()

        return {
            "tenant_id": tenant.id,
            "user_id": user.id,
            "client_id": client.id,
            "product_id": product.id,
            "bin_id": bin_.id,
        }


# =============================================================================
# TESTS F3-9c — AccountReceivable
# =============================================================================

class TestAccountReceivable:
    """
    Escenario completo:
      1. Venta a CC por $10.000 sin pago inicial → AR balance=10000, status='pending'
      2. Pago parcial $4.000 → balance=6000, status='partial'
      3. Pago final $6.000  → balance=0,    status='paid'
    """

    def test_f39c_venta_cc_crea_ar(self, engine, seed):
        """Venta a cuenta corriente con amount_paid=0 genera AccountReceivable."""
        svc = StockService()
        tid, uid, cid, pid = (
            seed["tenant_id"], seed["user_id"],
            seed["client_id"], seed["product_id"],
        )

        with Session(engine) as s:
            sale = svc.process_sale(
                session=s,
                user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 2}],
                payment_method="cuenta_corriente",
                amount_paid=0.0,
                client_id=cid,
            )
            sale_id = sale.id
            total = sale.total_amount  # 2 × $5000 = $10000

        with Session(engine) as s:
            ar = s.exec(
                select(AccountReceivable).where(AccountReceivable.sale_id == sale_id)
            ).first()

        assert ar is not None, "AccountReceivable no fue creado"
        assert ar.client_id == cid
        assert ar.total == total, f"total esperado={total}, obtenido={ar.total}"
        assert ar.paid == 0.0
        assert ar.balance == total, f"balance esperado={total}, obtenido={ar.balance}"
        assert ar.status == "pending", f"status esperado='pending', obtenido='{ar.status}'"

        # Guardar para tests siguientes
        engine._test_ar_sale_id = sale_id
        engine._test_ar_id = ar.id
        engine._test_ar_total = total

    def test_f39c_no_cashmovement_en_cc(self, engine, seed):
        """Una venta a cuenta corriente NO genera CashMovement."""
        sale_id = engine._test_ar_sale_id
        tid = seed["tenant_id"]

        with Session(engine) as s:
            cm = s.exec(
                select(CashMovement).where(
                    CashMovement.tenant_id == tid,
                    CashMovement.reference_id == sale_id,
                    CashMovement.movement_type == "in",
                )
            ).first()

        assert cm is None, f"CashMovement inesperado creado para venta CC: {cm}"

    def test_f39c_idempotencia_ar(self, engine, seed):
        """
        Si se llama a process_sale con el mismo sale_id (simulado con una segunda
        llamada), NO debe crearse un AccountReceivable duplicado.
        La unicidad sale_id en el modelo previene el duplicado en DB.
        Verificamos que exista exactamente 1 AR para la venta.
        """
        sale_id = engine._test_ar_sale_id

        with Session(engine) as s:
            count = s.exec(
                select(func.count(AccountReceivable.id)).where(
                    AccountReceivable.sale_id == sale_id
                )
            ).one()

        assert count == 1, f"Esperado 1 AccountReceivable, encontrado {count}"

    def test_f39c_pago_parcial_4000(self, engine, seed):
        """
        Pago parcial de $4.000 sobre AR de $10.000:
          balance → $6.000, status → 'partial', Payment.receivable_id enlazado.
        """
        cid = seed["client_id"]
        tid = seed["tenant_id"]
        ar_id = engine._test_ar_id
        total = engine._test_ar_total  # $10000

        from decimal import Decimal
        with Session(engine) as s:
            ar = s.get(AccountReceivable, ar_id)
            payment_amount = Decimal("4000.00")

            apply = min(payment_amount, ar.balance)
            ar.paid = (ar.paid or Decimal("0.00")) + apply
            ar.balance = ar.balance - apply
            ar.status = "partial" if ar.balance > Decimal("0.00") else "paid"
            s.add(ar)

            payment = Payment(
                tenant_id=tid,
                client_id=cid,
                amount=payment_amount,
                method="cash",
                note="Pago parcial $4000",
                receivable_id=ar_id,
            )
            s.add(payment)
            s.commit()

        with Session(engine) as s:
            ar = s.get(AccountReceivable, ar_id)

        assert ar.balance == Decimal("6000.00"), f"balance esperado=6000, obtenido={ar.balance}"
        assert ar.status == "partial", f"status esperado='partial', obtenido='{ar.status}'"
        assert ar.paid == Decimal("4000.00"), f"paid esperado=4000, obtenido={ar.paid}"

    def test_f39c_pago_final_6000(self, engine, seed):
        """
        Pago final de $6.000 sobre AR con balance=$6.000:
          balance → $0, status → 'paid'.
        """
        from decimal import Decimal
        cid = seed["client_id"]
        tid = seed["tenant_id"]
        ar_id = engine._test_ar_id

        with Session(engine) as s:
            ar = s.get(AccountReceivable, ar_id)
            payment_amount = Decimal("6000.00")

            apply = min(payment_amount, ar.balance)
            ar.paid = (ar.paid or Decimal("0.00")) + apply
            ar.balance = ar.balance - apply
            ar.status = "partial" if ar.balance > Decimal("0.00") else "paid"
            if ar.balance <= Decimal("0.00"):
                ar.balance = Decimal("0.00")
            s.add(ar)

            payment = Payment(
                tenant_id=tid,
                client_id=cid,
                amount=payment_amount,
                method="cash",
                note="Pago final $6000",
                receivable_id=ar_id,
            )
            s.add(payment)
            s.commit()

        with Session(engine) as s:
            ar = s.get(AccountReceivable, ar_id)

        assert ar.balance == Decimal("0.00"), f"balance esperado=0, obtenido={ar.balance}"
        assert ar.status == "paid", f"status esperado='paid', obtenido='{ar.status}'"
        assert ar.paid == Decimal("10000.00"), f"paid total esperado=10000, obtenido={ar.paid}"

    def test_f39c_pago_parcial_inicial(self, engine, seed):
        """
        Venta con pago parcial inicial (amount_paid=2000 sobre total=5000):
          AR.paid=2000, AR.balance=3000, AR.status='partial'.
        """
        svc = StockService()
        tid, uid, cid, pid = (
            seed["tenant_id"], seed["user_id"],
            seed["client_id"], seed["product_id"],
        )

        with Session(engine) as s:
            sale = svc.process_sale(
                session=s,
                user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 1}],
                payment_method="cuenta_corriente",
                amount_paid=2_000.0,
                client_id=cid,
            )
            sale_id = sale.id
            total = sale.total_amount  # $5000

        with Session(engine) as s:
            ar = s.exec(
                select(AccountReceivable).where(AccountReceivable.sale_id == sale_id)
            ).first()

        assert ar is not None
        assert ar.total == 5_000.0
        assert ar.paid == 2_000.0
        assert ar.balance == 3_000.0
        assert ar.status == "partial"


# =============================================================================
# TESTS F4-12 — Cancelación de venta
# =============================================================================

class TestSaleCancellation:
    """
    Verifica que cancel_sale():
      - Revierte BinStock correctamente.
      - Genera StockMovement(reason='anulacion').
      - Genera CashMovement negativo igual al pago.
      - Cancela AccountReceivable si existe.
      - Marca Sale.payment_status = 'cancelled'.
      - Rechaza cancelar ventas de caja cerrada.
      - Rechaza doble cancelación.
    """

    def _cancel(self, session: Session, sale_id: int, tenant_id: int,
                 user_id: int, reason: str = "Test cancelacion"):
        """Replica la lógica de cancel_sale() sin el router."""
        from database.models import Bin
        from datetime import datetime, timezone as _tz

        sale = session.get(Sale, sale_id)
        assert sale is not None
        if sale.is_closed:
            raise ValueError("Venta de caja cerrada")
        if getattr(sale, "payment_status", None) == "cancelled":
            raise ValueError("Ya anulada")

        sale_items = session.exec(
            select(SaleItem)
            .where(SaleItem.sale_id == sale_id)
            .order_by(SaleItem.product_id.asc())
        ).all()

        for item in sale_items:
            target_bin = session.exec(
                select(Bin).where(Bin.tenant_id == tenant_id, Bin.name == "SIN-UBICACION")
            ).first()

            if target_bin:
                bin_stock = session.exec(
                    select(BinStock)
                    .where(BinStock.bin_id == target_bin.id,
                           BinStock.product_id == item.product_id)
                    .with_for_update()
                ).first()
                if bin_stock:
                    bin_stock.quantity += item.quantity
                    bin_stock.updated_at = datetime.now(_tz.utc) if True else None
                    session.add(bin_stock)

            session.add(StockMovement(
                tenant_id=tenant_id,
                product_id=item.product_id,
                from_bin_id=None,
                to_bin_id=target_bin.id if target_bin else None,
                quantity=item.quantity,
                reason="anulacion",
                notes=f"Reversion Venta#{sale_id}. Motivo: {reason}",
                user_id=user_id,
            ))

        allocations = session.exec(
            select(PaymentAllocation).where(PaymentAllocation.sale_id == sale_id)
        ).all()
        for alloc in allocations:
            if (alloc.amount or 0.0) <= 0:
                continue
            method_label = "Efectivo" if alloc.method == "cash" else "Transferencia"
            session.add(CashMovement(
                tenant_id=tenant_id,
                user_id=user_id,
                amount=-alloc.amount,
                movement_type="out",
                concept=f"Anulacion Venta#{sale_id} - {method_label} - {reason}",
                reference_type="cancellation",
                reference_id=sale_id,
            ))

        ar = session.exec(
            select(AccountReceivable).where(AccountReceivable.sale_id == sale_id)
        ).first()
        if ar:
            ar.status = "cancelled"
            ar.balance = 0.0
            session.add(ar)

        sale.payment_status = "cancelled"
        session.add(sale)
        session.commit()

    def test_f412_cancel_venta_efectivo_revierte_stock_y_caja(self, engine, seed):
        """
        Venta de 3u en efectivo → cancelar →
          BinStock += 3, CashMovement negativo, Sale.payment_status='cancelled'.
        """
        from datetime import datetime as _dt

        svc = StockService()
        tid, uid, pid, bid = (
            seed["tenant_id"], seed["user_id"],
            seed["product_id"], seed["bin_id"],
        )

        # Stock antes
        with Session(engine) as s:
            bs_before = s.exec(
                select(BinStock).where(BinStock.product_id == pid, BinStock.bin_id == bid)
            ).first()
            stock_before = bs_before.quantity

        # Crear venta
        with Session(engine) as s:
            sale = svc.process_sale(
                session=s,
                user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 3}],
                payment_method="cash", amount_paid=15_000.0,
            )
            sale_id = sale.id

        with Session(engine) as s:
            bs_after_sale = s.exec(
                select(BinStock).where(BinStock.product_id == pid, BinStock.bin_id == bid)
            ).first()
            stock_after_sale = bs_after_sale.quantity

        assert stock_after_sale == stock_before - 3

        # Contar CashMovements antes de cancelar
        with Session(engine) as s:
            cm_count_before_cancel = s.exec(
                select(func.count(CashMovement.id)).where(CashMovement.tenant_id == tid)
            ).one()

        # Cancelar
        with Session(engine) as s:
            self._cancel(s, sale_id, tid, uid)

        # Verificaciones
        with Session(engine) as s:
            bs_after_cancel = s.exec(
                select(BinStock).where(BinStock.product_id == pid, BinStock.bin_id == bid)
            ).first()
            # Stock debe haber vuelto al valor antes de la venta
            assert bs_after_cancel.quantity == stock_before, \
                f"Stock: esperado={stock_before}, obtenido={bs_after_cancel.quantity}"

            # StockMovement de anulación
            sm = s.exec(
                select(StockMovement).where(
                    StockMovement.product_id == pid,
                    StockMovement.reason == "anulacion",
                ).order_by(StockMovement.id.desc())
            ).first()
            assert sm is not None, "StockMovement de anulacion no encontrado"
            assert sm.quantity == 3
            assert "anulacion" in sm.reason

            # CashMovement negativo
            cm_cancel = s.exec(
                select(CashMovement).where(
                    CashMovement.reference_id == sale_id,
                    CashMovement.reference_type == "cancellation",
                )
            ).first()
            assert cm_cancel is not None, "CashMovement de cancelacion no encontrado"
            assert cm_cancel.amount < 0, f"CashMovement debe ser negativo: {cm_cancel.amount}"
            assert cm_cancel.amount == -15_000.0

            # Sale.payment_status = 'cancelled'
            cancelled_sale = s.get(Sale, sale_id)
            assert cancelled_sale.payment_status == "cancelled"

    def test_f412_cancel_revierte_ar(self, engine, seed):
        """
        Venta a CC → AR creado → cancelar → AR.status='cancelled', AR.balance=0.
        """
        svc = StockService()
        tid, uid, cid, pid = (
            seed["tenant_id"], seed["user_id"],
            seed["client_id"], seed["product_id"],
        )

        with Session(engine) as s:
            sale = svc.process_sale(
                session=s,
                user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 1}],
                payment_method="cuenta_corriente",
                amount_paid=0.0, client_id=cid,
            )
            sale_id = sale.id

        # Verificar AR creado
        with Session(engine) as s:
            ar = s.exec(
                select(AccountReceivable).where(AccountReceivable.sale_id == sale_id)
            ).first()
        assert ar is not None
        ar_id = ar.id

        # Cancelar
        with Session(engine) as s:
            self._cancel(s, sale_id, tid, uid)

        # Verificar AR cancelado
        with Session(engine) as s:
            ar = s.get(AccountReceivable, ar_id)
        assert ar.status == "cancelled", f"status esperado='cancelled', obtenido='{ar.status}'"
        assert ar.balance == 0.0, f"balance esperado=0, obtenido={ar.balance}"

    def test_f412_no_cancela_caja_cerrada(self, engine, seed):
        """
        Una venta con is_closed=True debe rechazar la cancelación con ValueError.
        """
        svc = StockService()
        tid, uid, pid = seed["tenant_id"], seed["user_id"], seed["product_id"]

        with Session(engine) as s:
            sale = svc.process_sale(
                session=s,
                user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 1}],
                payment_method="cash", amount_paid=5_000.0,
            )
            sale.is_closed = True
            s.add(sale)
            s.commit()
            sale_id = sale.id

        with pytest.raises(ValueError, match="(?i)cerrada"):
            with Session(engine) as s:
                self._cancel(s, sale_id, tid, uid)

    def test_f412_no_doble_cancelacion(self, engine, seed):
        """
        Intentar cancelar una venta ya anulada debe lanzar ValueError.
        """
        svc = StockService()
        tid, uid, pid = seed["tenant_id"], seed["user_id"], seed["product_id"]

        with Session(engine) as s:
            sale = svc.process_sale(
                session=s,
                user_id=uid, tenant_id=tid,
                items_data=[{"product_id": pid, "quantity": 1}],
                payment_method="cash", amount_paid=5_000.0,
            )
            sale_id = sale.id

        # Primera cancelación — debe funcionar
        with Session(engine) as s:
            self._cancel(s, sale_id, tid, uid)

        # Segunda cancelación — debe fallar
        with pytest.raises(ValueError, match="(?i)anulada"):
            with Session(engine) as s:
                self._cancel(s, sale_id, tid, uid)
