import barcode
from barcode.writer import ImageWriter
from sqlmodel import Session, select
from database.models import Product, Sale, SaleItem, User, Payment, CashMovement
from typing import List, Optional
import os
from datetime import datetime

class StockService:
    def __init__(self, static_dir: str = "static/barcodes"):
        self.static_dir = static_dir
        os.makedirs(self.static_dir, exist_ok=True)

    def generate_barcode(self, product_id: int) -> str:
        """
        Generates a barcode for a product_id. 
        Returns the filename of the generated barcode image.
        Format: EAN13 (or Code128 if preferred).
        """
        # Switch to SVG for perfect scalability and print quality
        # No writer specified = Default SVGWriter (vectors)
        code = barcode.get('code128', str(product_id).zfill(8))
        filename = f"product_{product_id}"
        full_path = os.path.join(self.static_dir, filename)
        code.save(full_path) # saves as filename.svg
        return f"{filename}.svg"

    def process_sale(self, session: Session, user_id: int, tenant_id: int, items_data: List[dict], payment_method: str = "cash", client_id: Optional[int] = None, amount_paid: Optional[float] = None, split_cash: Optional[float] = None, split_transfer: Optional[float] = None) -> Sale:
        """
        Creates a Sale record and updates product stock.

        - If client_id is provided and amount_paid > 0, creates a Payment record.
        - If client_id is provided and final_amount_paid < total_sale, creates an
          AccountReceivable to formally track the outstanding debt (F3-9c fix).
          Idempotent: skips creation if an AccountReceivable already exists for
          this sale_id (safe against retries).
        - items_data expected format: [{"product_id": 1, "quantity": 2}, ...]

        Concurrency safety: each BinStock row is locked with SELECT FOR UPDATE before
        the stock check and decrement, serializing concurrent sales of the same product.
        Items are sorted by product_id ascending to acquire locks in a consistent order
        and prevent deadlocks between concurrent sales sharing products.
        """
        from datetime import timezone
        from decimal import Decimal
        from database.models import Bin, BinStock, StockMovement, AccountReceivable

        sale = Sale(tenant_id=tenant_id, user_id=user_id, payment_method=payment_method, client_id=client_id, timestamp=datetime.now(timezone.utc))
        total_sale = Decimal("0.00")

        # ── Deadlock prevention: acquire locks in consistent product_id order ──────
        items_data = sorted(items_data, key=lambda i: i["product_id"])

        for item in items_data:
            p_id = item["product_id"]
            qty = item["quantity"]
            
            # Verify product belongs to tenant
            product = session.exec(select(Product).where(Product.id == p_id, Product.tenant_id == tenant_id)).first()
            if not product:
                raise ValueError(f"Product {p_id} not found or access denied")
            
            # Determine Price: Explicitly honor price_type if sent from POS
            price_type = item.get("price_type")
            if price_type == "bulk" and product.price_bulk and product.price_bulk > Decimal("0.00"):
                unit_price = Decimal(str(product.price_bulk))
            elif price_type == "retail" and product.price_retail and product.price_retail > Decimal("0.00"):
                unit_price = Decimal(str(product.price_retail))
            elif product.price_bulk and product.price_bulk > Decimal("0.00") and product.cant_bulto and qty >= product.cant_bulto:
                unit_price = Decimal(str(product.price_bulk))
            else:
                unit_price = Decimal(str(product.price))

            # ── SECCIÓN CRÍTICA: SELECT FOR UPDATE ───────────────────────────────
            target_bin = session.exec(
                select(Bin).where(Bin.tenant_id == tenant_id, Bin.name == "SIN-UBICACION")
            ).first()
            if not target_bin:
                target_bin = session.exec(
                    select(Bin).where(Bin.tenant_id == tenant_id, Bin.is_active == True)
                ).first()
            if not target_bin:
                raise ValueError("No hay ubicaciones configuradas para descontar stock.")

            locked_bin_stock = session.exec(
                select(BinStock)
                .where(
                    BinStock.bin_id == target_bin.id,
                    BinStock.product_id == p_id,
                )
                .with_for_update()
            ).first()

            available = locked_bin_stock.quantity if locked_bin_stock else 0
            if available < qty:
                raise ValueError(
                    f"Insufficient stock for {product.name}. "
                    f"Available: {available}, Requested: {qty}"
                )

            locked_bin_stock.quantity -= qty
            locked_bin_stock.updated_at = datetime.now(timezone.utc)
            session.add(locked_bin_stock)

            session.add(StockMovement(
                tenant_id=tenant_id,
                product_id=p_id,
                from_bin_id=target_bin.id,
                to_bin_id=None,
                quantity=qty,
                reason="venta",
                notes="Salida por venta",
                user_id=user_id,
            ))
            # ── FIN SECCIÓN CRÍTICA ──────────────────────────────────────────────

            line_total = unit_price * Decimal(qty)
            total_sale += line_total
            
            sale_item = SaleItem(
                product_id=p_id,
                product_name=product.name,
                quantity=qty,
                unit_price=unit_price,
                total=line_total,
                cost_price_at_sale=Decimal(str(product.cost_price or "0.00"))
            )
            sale.items.append(sale_item)
            
        sale.total_amount = total_sale
        
        # Payment Logic
        if split_cash is not None or split_transfer is not None:
            amt_cash = Decimal(str(split_cash)) if split_cash is not None else Decimal("0.00")
            amt_transfer = Decimal(str(split_transfer)) if split_transfer is not None else Decimal("0.00")
            final_amount_paid = amt_cash + amt_transfer
            if amt_cash > Decimal("0.00") and amt_transfer == Decimal("0.00"):
                sale.payment_method = "cash"
            elif amt_transfer > Decimal("0.00") and amt_cash == Decimal("0.00"):
                sale.payment_method = "transfer"
            elif amt_cash == Decimal("0.00") and amt_transfer == Decimal("0.00"):
                sale.payment_method = "cuenta_corriente"
            else:
                sale.payment_method = "combinado"
        else:
            final_amount_paid = Decimal(str(amount_paid)) if amount_paid is not None else total_sale
            amt_cash = final_amount_paid if payment_method == "cash" else Decimal("0.00")
            amt_transfer = final_amount_paid if payment_method == "transfer" else Decimal("0.00")
            sale.payment_method = payment_method
        
        # --- Credit Limit & Authorization Check (Riesgo 1) ---
        client = None
        if client_id:
            from database.models import Client, User
            from sqlalchemy import func
            client = session.exec(
                select(Client)
                .where(Client.id == client_id, Client.tenant_id == tenant_id)
                .with_for_update()
            ).first()
            
        if client and final_amount_paid < total_sale:
            sale_user = session.get(User, user_id)
            if sale_user and sale_user.role == "client":
                linked_client_id = getattr(sale_user, "client_id", None)
                if linked_client_id != client_id:
                    raise ValueError("Acceso denegado: no podés realizar compras a crédito a nombre de otro cliente.")

            if not getattr(client, "credit_enabled", False):
                raise ValueError("Tu cuenta no tiene cuenta corriente habilitada, contactá a un administrador.")

            if client.tenant_id == tenant_id and client.credit_limit is not None:
                 from database.models import AccountReceivable
                 stmt_ar = select(func.sum(AccountReceivable.balance)).where(
                     AccountReceivable.client_id == client_id,
                     AccountReceivable.tenant_id == tenant_id,
                     AccountReceivable.status.in_(["pending", "partial"])
                 )
                 raw_deuda = session.exec(stmt_ar).one()
                 deuda_actual = Decimal(str(raw_deuda)) if raw_deuda is not None else Decimal("0.00")
                 deuda_nueva = total_sale - final_amount_paid
                 
                 if (deuda_actual + deuda_nueva) > Decimal(str(client.credit_limit)):
                     credito_disponible = max(Decimal(str(client.credit_limit)) - deuda_actual, Decimal("0.00"))
                     raise ValueError(
                         f"Límite de crédito excedido. Disponible: ${credito_disponible:.2f}, "
                         f"deuda solicitada: ${deuda_nueva:.2f}"
                     )

        # Determine Status
        if final_amount_paid >= total_sale:
            sale.payment_status = "paid"
        elif final_amount_paid > Decimal("0.00"):
            sale.payment_status = "partial"
        else:
            sale.payment_status = "pending"
            
        sale.amount_paid = final_amount_paid
        
        from database.models import PaymentAllocation
        if amt_cash > Decimal("0.00"):
            sale.payment_allocations.append(PaymentAllocation(method="cash", amount=amt_cash))
        if amt_transfer > Decimal("0.00"):
            sale.payment_allocations.append(PaymentAllocation(method="transfer", amount=amt_transfer))
        
        session.add(sale)
        session.flush()
        
        # Handle Payment if Client is selected
        if client_id and final_amount_paid > Decimal("0.00"):
            payment = Payment(
                tenant_id=tenant_id,
                client_id=client_id,
                amount=final_amount_paid,
                date=datetime.now(),
                note=f"Pago inmediato en Venta" 
            )
            session.add(payment)
            
        # Register in Cash Book
        if final_amount_paid > Decimal("0.00"):
            from database.models import CashMovement
            client_name = client.name if client else "Consumidor Final"
            
            if amt_cash > Decimal("0.00"):
                session.add(CashMovement(
                    tenant_id=tenant_id, user_id=user_id, amount=amt_cash,
                    movement_type="in", concept=f"Ingreso por Venta a {client_name} - Medio: Efectivo",
                    reference_type="sale", reference_id=sale.id
                ))
            if amt_transfer > Decimal("0.00"):
                session.add(CashMovement(
                    tenant_id=tenant_id, user_id=user_id, amount=amt_transfer,
                    movement_type="in", concept=f"Ingreso por Venta a {client_name} - Medio: Transferencia",
                    reference_type="sale", reference_id=sale.id
                ))

        if client_id and final_amount_paid < total_sale:
            existing_ar = session.exec(
                select(AccountReceivable).where(AccountReceivable.sale_id == sale.id)
            ).first()
            if not existing_ar:
                debt = total_sale - final_amount_paid
                session.add(AccountReceivable(
                    tenant_id=tenant_id,
                    sale_id=sale.id,
                    client_id=client_id,
                    total=total_sale,
                    paid=final_amount_paid,
                    balance=debt,
                    status="partial" if final_amount_paid > Decimal("0.00") else "pending",
                ))
        session.commit()
        return sale
        # ── FIN F3-9c ─────────────────────────────────────────────────────────────

        # Single commit for the entire sale transaction
        # (stock + kardex + sale + payments + account_receivable).
        session.commit()
        return sale

    def get_total_stock(self, session: Session, product_id: int, tenant_id: int) -> int:
        from database.models import BinStock
        from sqlalchemy import func
        total = session.exec(select(func.sum(BinStock.quantity)).where(BinStock.product_id == product_id, BinStock.tenant_id == tenant_id)).one()
        return total or 0

    def add_stock(self, session: Session, product_id: int, tenant_id: int, quantity: int, reason: str, notes: str, user_id: int = None):
        """
        Helper for non-sale stock adjustments (e.g. purchases, manual corrections).
        NOT used by process_sale — sales use inline SELECT FOR UPDATE for atomicity.
        Delegates to BinStockService.adjust_stock which manages its own commit.
        """
        if quantity == 0: return
        from services.bin_stock_service import BinStockService
        from database.models import Bin
        bin_ = session.exec(select(Bin).where(Bin.tenant_id == tenant_id, Bin.name == "SIN-UBICACION")).first()
        if not bin_:
            bin_ = session.exec(select(Bin).where(Bin.tenant_id == tenant_id, Bin.is_active == True)).first()
        if not bin_:
            raise ValueError("No hay ubicaciones configuradas para descontar stock.")
        
        from database.models import BinStock
        current_bs = session.exec(select(BinStock).where(BinStock.bin_id == bin_.id, BinStock.product_id == product_id)).first()
        current_qty = current_bs.quantity if current_bs else 0
        new_qty = current_qty + quantity
        BinStockService.adjust_stock(session, tenant_id, bin_.id, product_id, new_qty, reason, notes, user_id)
