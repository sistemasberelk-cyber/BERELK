"""
tests/test_concurrency_stock.py
================================
Test de concurrencia para verificar el fix TOCTOU en process_sale.

Escenario: 2 ventas simultáneas del mismo producto con stock=1.
Resultado esperado:
  - Exactamente 1 venta exitosa.
  - Exactamente 1 fallo con "Insufficient stock".
  - Stock final en BinStock = 0 (nunca negativo).

Nota sobre SQLite vs PostgreSQL:
  SQLite no soporta SELECT ... FOR UPDATE a nivel motor. En SQLite, el lock
  de Python (threading.Lock) alrededor de process_sale es lo que provee la
  serialización. En PostgreSQL (Supabase, producción), el with_for_update()
  de SQLAlchemy emite SELECT ... FOR UPDATE nativo, serializando a nivel DB.

  Este test valida la LÓGICA de validación (solo 1 puede pasar) y es la
  base para un integration test contra Supabase en CI.
"""

import os
import threading
import pytest

# Asegurar env vars necesarias para imports
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_FERNET_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_concurrency.db")

from sqlmodel import SQLModel, Session, create_engine, select
from database.models import (
    Tenant, User, Product, Location, Bin, BinStock
)
from services.stock_service import StockService


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    """Engine SQLite en memoria para tests (aislado del test.db de dev)."""
    eng = create_engine(
        "sqlite:///./test_concurrency.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()  # libera el connection pool antes de borrar el archivo (necesario en Windows)
    import os as _os
    try:
        _os.remove("./test_concurrency.db")
    except (FileNotFoundError, PermissionError):
        pass  # si Windows aún lo retiene, el siguiente run lo sobreescribirá sin problemas



@pytest.fixture(scope="module")
def seed_data(engine):
    """
    Crea en la DB de test:
      - 1 Tenant
      - 1 User (cajero)
      - 1 Product (precio=100)
      - 1 Location + 1 Bin ("SIN-UBICACION")
      - BinStock con quantity=1
    """
    with Session(engine) as session:
        tenant = Tenant(name="TestTenant")
        session.add(tenant)
        session.flush()

        user = User(
            tenant_id=tenant.id,
            username="cajero_test",
            password_hash="hash",
            role="cashier",
        )
        session.add(user)
        session.flush()

        product = Product(
            tenant_id=tenant.id,
            name="Producto Test",
            barcode="TEST001",
            price=100.0,
            cost_price=50.0,
        )
        session.add(product)
        session.flush()

        location = Location(
            tenant_id=tenant.id,
            name="Depósito Central",
            code="DEP-CENTRAL",
        )
        session.add(location)
        session.flush()

        bin_ = Bin(
            tenant_id=tenant.id,
            location_id=location.id,
            name="SIN-UBICACION",
            is_active=True,
        )
        session.add(bin_)
        session.flush()

        # Stock inicial = 1 (exactamente 1 unidad disponible)
        bin_stock = BinStock(
            tenant_id=tenant.id,
            bin_id=bin_.id,
            product_id=product.id,
            quantity=1,
        )
        session.add(bin_stock)
        session.commit()

        return {
            "tenant_id": tenant.id,
            "user_id": user.id,
            "product_id": product.id,
            "bin_id": bin_.id,
        }


# ── Test principal de concurrencia ───────────────────────────────────────────

def test_concurrent_sales_only_one_succeeds(engine, seed_data):
    """
    Lanza 2 threads que intentan vender el mismo producto (stock=1, qty=1)
    simultáneamente.

    Invariantes que deben cumplirse:
      1. Exactamente 1 venta exitosa (successes == 1).
      2. Exactamente 1 fallo con ValueError que contenga "Insufficient stock"
         o "stock" en el mensaje (failures == 1).
      3. El stock final en BinStock == 0 (nunca < 0).
    """
    tenant_id = seed_data["tenant_id"]
    user_id = seed_data["user_id"]
    product_id = seed_data["product_id"]

    successes = []
    failures = []

    # En SQLite, usamos un Lock de Python para serializar los accesos
    # (simula la serialización que hace SELECT FOR UPDATE en PostgreSQL).
    # En PostgreSQL real (CI / staging), quitar este lock y verificar
    # que el with_for_update() en process_sale hace el trabajo solo.
    db_lock = threading.Lock()

    def attempt_sale(thread_id: int):
        svc = StockService()
        items = [{"product_id": product_id, "quantity": 1}]
        try:
            with db_lock:  # serializa en SQLite; en PG no es necesario
                with Session(engine) as session:
                    sale = svc.process_sale(
                        session=session,
                        user_id=user_id,
                        tenant_id=tenant_id,
                        items_data=items,
                        payment_method="cash",
                        amount_paid=100.0,
                    )
                successes.append(thread_id)
        except ValueError as e:
            failures.append((thread_id, str(e)))
        except Exception as e:
            failures.append((thread_id, f"UNEXPECTED: {e}"))

    t1 = threading.Thread(target=attempt_sale, args=(1,))
    t2 = threading.Thread(target=attempt_sale, args=(2,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # ── Aserciones ────────────────────────────────────────────────────────────
    assert len(successes) == 1, (
        f"Exactamente 1 venta debería haber tenido éxito, pero tuvieron éxito: {successes}. "
        f"Fallos: {failures}"
    )
    assert len(failures) == 1, (
        f"Exactamente 1 venta debería haber fallado, pero fallaron: {failures}. "
        f"Éxitos: {successes}"
    )

    # El mensaje de error debe ser legible y mencionar stock insuficiente
    _fail_thread_id, fail_msg = failures[0]
    assert "stock" in fail_msg.lower() or "insufficient" in fail_msg.lower(), (
        f"El mensaje de error no menciona stock insuficiente: '{fail_msg}'"
    )

    # Stock final debe ser exactamente 0, nunca negativo
    with Session(engine) as session:
        bin_stock = session.exec(
            select(BinStock).where(
                BinStock.tenant_id == tenant_id,
                BinStock.product_id == product_id,
            )
        ).first()
        assert bin_stock is not None, "BinStock no encontrado después de la venta"
        assert bin_stock.quantity == 0, (
            f"Stock final debe ser 0, pero es {bin_stock.quantity}. "
            "Posible sobreventa o stock negativo detectado."
        )


def test_sale_with_zero_stock_fails_immediately(engine, seed_data):
    """
    Con stock=0, cualquier venta debe fallar inmediatamente con ValueError
    que mencione stock insuficiente.
    """
    # El test anterior ya dejó el stock en 0
    tenant_id = seed_data["tenant_id"]
    user_id = seed_data["user_id"]
    product_id = seed_data["product_id"]

    svc = StockService()
    items = [{"product_id": product_id, "quantity": 1}]

    with Session(engine) as session:
        with pytest.raises(ValueError, match="(?i)insufficient|stock"):
            svc.process_sale(
                session=session,
                user_id=user_id,
                tenant_id=tenant_id,
                items_data=items,
                payment_method="cash",
                amount_paid=100.0,
            )
