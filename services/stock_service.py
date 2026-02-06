import barcode
from barcode.writer import ImageWriter
from sqlmodel import Session, select
from database.models import Product, Sale, SaleItem, User, Payment
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
        # Simple generation using ID padded to 12 digits (EAN13 requires 12 + check digit)
        # Using Code128 for flexibility with IDs
        code = barcode.get('code128', str(product_id).zfill(8), writer=ImageWriter())
        filename = f"product_{product_id}"
        full_path = os.path.join(self.static_dir, filename)
        code.save(full_path)
        return f"{filename}.png"

    def process_sale(self, session: Session, user_id: int, items_data: List[dict], payment_method: str = "cash", client_id: Optional[int] = None, amount_paid: Optional[float] = None) -> Sale:
        """
        Creates a Sale record and updates product stock.
        If client_id is provided and amount_paid > 0, creates a Payment record.
        items_data expected format: [{"product_id": 1, "quantity": 2}, ...]
        """
        sale = Sale(user_id=user_id, payment_method=payment_method, client_id=client_id, timestamp=datetime.now())
        total_sale = 0.0
        
        for item in items_data:
            p_id = item["product_id"]
            qty = item["quantity"]
            
            product = session.get(Product, p_id)
            if not product:
                raise ValueError(f"Product {p_id} not found")
            
            if product.stock_quantity < qty:
                raise ValueError(f"Insufficient stock for {product.name}")
            
            # --- Credit Limit Check ---
            # If sale is not fully paid (Current Account), check limit
            # Calculate what part is debt
            pending_amount = (total_sale + (product.price * qty)) - (amount_paid or 0) 
            # Note: total_sale is accumulating in this loop, so this check is tricky inside loop.
            # Better to check at the end or pre-calculate. 
            # Optimization: Let's do it after calculating total_sale completely.
            
            # Decrement Stock
            product.stock_quantity -= qty
            session.add(product)
            
            # Create Sale Item
            line_total = product.price * qty
            total_sale += line_total
            
            sale_item = SaleItem(
                product_id=p_id,
                product_name=product.name,
                quantity=qty,
                unit_price=product.price,
                total=line_total
            )
            sale.items.append(sale_item)
            
        sale.total_amount = total_sale
        
        # Payment Logic
        final_amount_paid = amount_paid if amount_paid is not None else total_sale
        
        # --- Credit Limit Check ---
        if client_id and final_amount_paid < total_sale:
            from database.models import Client
            from sqlalchemy import func
            client = session.get(Client, client_id)
            if client and client.credit_limit:
                 # Calculate current balance (Debt - Paid)
                 # This logic mirrors main.py/clients logic
                 # Note: Ideally this balance calculation should be a method on Client or Service
                 
                 # Sum previous sales total
                 stmt_sales = select(func.sum(Sale.total_amount)).where(Sale.client_id == client_id)
                 current_debt = session.exec(stmt_sales).one() or 0.0
                 
                 # Sum payments
                 stmt_payments = select(func.sum(Payment.amount)).where(Payment.client_id == client_id)
                 current_paid = session.exec(stmt_payments).one() or 0.0
                 
                 current_balance = current_debt - current_paid
                 new_debt = total_sale - final_amount_paid
                 
                 if (current_balance + new_debt) > client.credit_limit:
                     raise ValueError(f"Credit Limit Exceeded. Limit: ${client.credit_limit}, Current Balance: ${current_balance}, New Debt: ${new_debt}")

        # Determine Status
        if final_amount_paid >= total_sale:
            sale.payment_status = "paid"
        elif final_amount_paid > 0:
            sale.payment_status = "partial"
        else:
            sale.payment_status = "pending"
            
        sale.amount_paid = final_amount_paid
        
        session.add(sale)
        
        # Handle Payment if Client is selected
        if client_id and final_amount_paid > 0:
            # Create a payment record linked to this sale (conceptually via time/client)
            # The Payment model needs client_id, amount. Note is optional.
            payment = Payment(
                client_id=client_id,
                amount=final_amount_paid,
                date=datetime.now(),
                note=f"Pago inmediato en Venta" 
            )
            session.add(payment)
            
        session.commit()
        session.refresh(sale)
        return sale
