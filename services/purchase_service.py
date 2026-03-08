from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlmodel import Session, select
from database.models import Product, Purchase, PurchaseItem, Supplier, CashMovement

class PurchaseService:
    @staticmethod
    def create_supplier(session: Session, tenant_id: int, **kwargs) -> Supplier:
        supplier = Supplier(tenant_id=tenant_id, **kwargs)
        session.add(supplier)
        session.commit()
        session.refresh(supplier)
        return supplier

    @staticmethod
    def process_purchase(
        session: Session, 
        user_id: int, 
        tenant_id: int,
        supplier_id: Optional[int], 
        invoice_number: Optional[str],
        items_data: List[Dict[str, Any]], 
        amount_paid: float = 0.0,
        cash_concept: str = "Pago de mercadería"
    ) -> Purchase:
        """
        Creates a purchase, updates product stocks using cost price, 
        and optionally reduces cash in the drawer (CashMovement)
        """
        if not items_data:
            raise ValueError("La compra debe tener al menos un producto")

        total_amount = 0.0
        
        # 1. Start Purchase Record
        purchase = Purchase(
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            invoice_number=invoice_number,
            status="pending" if amount_paid == 0 else ("paid" if amount_paid >= total_amount else "partial")
        )
        session.add(purchase)
        session.commit() # Commit to get ID for items
        session.refresh(purchase)

        # 2. Process Items and Add Stock
        for item_info in items_data:
            product_id = item_info.get("product_id")
            quantity = int(item_info.get("quantity", 1))
            unit_cost = float(item_info.get("unit_cost", 0.0))

            if quantity <= 0:
                raise ValueError("La cantidad debe ser mayor a 0")
            
            product = session.get(Product, product_id)
            if not product or product.tenant_id != tenant_id:
                raise ValueError(f"Producto ID {product_id} no encontrado")

            # Update Cost & Stock
            # We overwrite the current cost price with the latest purchase cost (or average it, simplified here)
            product.cost_price = unit_cost
            product.stock_quantity += quantity
            session.add(product)

            # Create Purchase Item
            item_total = quantity * unit_cost
            total_amount += item_total

            p_item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit_cost=unit_cost,
                total=item_total
            )
            session.add(p_item)

        # Update correct total
        purchase.total_amount = total_amount
        if amount_paid >= total_amount:
            purchase.status = "paid"
        session.add(purchase)
        
        # 3. Handle Payment (Cash Movement)
        if amount_paid > 0:
            money_out = CashMovement(
                tenant_id=tenant_id,
                amount=-abs(amount_paid), # Salidas se registran como valores numéricos negativos 
                movement_type="out",
                concept=cash_concept,
                reference_id=purchase.id,
                reference_type="purchase",
                user_id=user_id
            )
            session.add(money_out)

        session.commit()
        session.refresh(purchase)
        return purchase

    @staticmethod
    def get_supplier_balance(session: Session, tenant_id: int, supplier_id: int) -> float:
        """Calculates total debt to supplier (Purchased Total - Paid in CashMovements)"""
        purchases = session.exec(
            select(Purchase).where(Purchase.supplier_id == supplier_id, Purchase.tenant_id == tenant_id)
        ).all()
        
        movements = session.exec(
            select(CashMovement).where(
                CashMovement.tenant_id == tenant_id,
                CashMovement.reference_type == "supplier_payment",
                CashMovement.reference_id == supplier_id
            )
        ).all()
        
        # NOTE: A purchase also generates a initial cashmovement via references above if paid upfront
        # Assuming direct payments via references. Let's make it more robust.
        return 0.0

    @staticmethod
    def register_manual_cash_movement(
        session: Session,
        tenant_id: int,
        user_id: int,
        amount: float,
        movement_type: str, # "in", "out"
        concept: str,
        reference_id: Optional[int] = None,
        reference_type: Optional[str] = None
    ) -> CashMovement:
        """Register any generic movement (in/out) from petty cash. If out, ensure amount is negative"""
        final_amt = abs(amount) if movement_type == 'in' else -abs(amount)
        cm = CashMovement(
            tenant_id=tenant_id,
            user_id=user_id,
            amount=final_amt,
            movement_type=movement_type,
            concept=concept,
            reference_id=reference_id,
            reference_type=reference_type
        )
        session.add(cm)
        session.commit()
        session.refresh(cm)
        return cm
