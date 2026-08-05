"""routers/sales.py — Ventas + Cierre de Caja"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from database.models import (
    AccountReceivable, BinStock, CashMovement, PaymentAllocation,
    Product, Sale, SaleItem, Settings, StockMovement, User,
)
from database.session import get_session
from services.stock_service import StockService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth
from services.settings_service import SettingsService

router = APIRouter(tags=["Sales"])
stock_service = StockService(static_dir="static/barcodes")

def _templates():
    return CompatTemplates(directory="templates")

from services.sale_service import SaleService
from services.cash_service import CashService

from web.pagination import paginate

@router.get("/sales", response_class=HTMLResponse)
def get_sales_page(
    request: Request, 
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user: User = Depends(require_auth), 
    settings: Settings = Depends(get_settings), 
    tenant_id: int = Depends(get_tenant), 
    session: Session = Depends(get_session)
):
    query = select(Sale).where(Sale.tenant_id == tenant_id, Sale.is_closed == False).order_by(Sale.timestamp.desc())
    sales_page = paginate(session, query, page=page, size=size)
    
    low_stock_products = []
    for p in session.exec(select(Product).where(Product.tenant_id == tenant_id, Product.is_deleted == False)).all():
        stock = stock_service.get_total_stock(session, p.id, tenant_id)
        if stock < p.min_stock_level:
            p.stock_quantity = stock
            low_stock_products.append(p)
    
    return _templates().TemplateResponse("sales.html", {
        "request": request, 
        "active_page": "sales", 
        "settings": settings, 
        "user": user, 
        "sales": sales_page.items,
        "total": sales_page.total,
        "current_page": sales_page.page,
        "total_pages": sales_page.pages,
        "low_stock_products": low_stock_products, 
        "daily_reports": SaleService.build_daily_reports(session, tenant_id)
    })

@router.post("/sales/backup", response_class=HTMLResponse)
def trigger_backup(request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session)):
    from services.backup_service import perform_backup
    from services.database_backup_service import create_backup_file
    try:
        create_backup_file(session, tenant_id=tenant_id)
    except Exception as e:
        print(f"ERROR: Failed JSON backup: {e}")
    
    # Perform external backup
    result = perform_backup(session, tenant_id=tenant_id)
    
    # Execute closing logic using service
    CashService.perform_cierre(session, tenant_id, user.id)
    
    sales = session.exec(select(Sale).where(Sale.tenant_id == tenant_id, Sale.is_closed == False).order_by(Sale.timestamp.desc())).all()
    low_stock_products = []
    for p in session.exec(select(Product).where(Product.tenant_id == tenant_id, Product.is_deleted == False)).all():
        stock = stock_service.get_total_stock(session, p.id, tenant_id)
        if stock < p.min_stock_level:
            p.stock_quantity = stock
            low_stock_products.append(p)
    status_msg = "success" if result["status"] == "success" else "error"
    msg_text = "✅ Backup exitoso y caja cerrada!" if result["status"] == "success" else f"❌ Error: {result['message']}"
    return _templates().TemplateResponse("sales.html", {"request": request, "active_page": "sales", "settings": settings, "user": user, "sales": sales, "low_stock_products": low_stock_products, "daily_reports": SaleService.build_daily_reports(session, tenant_id), "backup_status": status_msg, "backup_message": msg_text})

@router.post("/api/sales")
def create_sale_api(sale_data: dict, session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    try:
        return stock_service.process_sale(session, user_id=user.id, tenant_id=tenant_id, items_data=sale_data["items"], client_id=sale_data.get("client_id"), amount_paid=sale_data.get("amount_paid"), payment_method=sale_data.get("payment_method", "cash"), split_cash=sale_data.get("split_cash"), split_transfer=sale_data.get("split_transfer"))
    except ValueError as e:
        msg = str(e)
        status_code = 403 if ("cuenta corriente" in msg.lower() or "denegado" in msg.lower() or "habilitada" in msg.lower() or "excedido" in msg.lower() or "límite" in msg.lower() or "limite" in msg.lower()) else 400
        raise HTTPException(status_code, msg)

@router.get("/sales/{id}/remito", response_class=HTMLResponse)
def get_sale_remito(id: int, request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session)):
    sale = session.get(Sale, id)
    if not sale or sale.tenant_id != tenant_id: raise HTTPException(404, "Sale not found")
    return _templates().TemplateResponse("remito.html", {"request": request, "sale": sale, "settings": settings})


@router.post("/api/sales/{id}/cancel")
def cancel_sale(
    id: int,
    reason: str = Form("Anulación manual"),
    session: Session = Depends(get_session),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
):
    """
    F4-12 FIX: Anulación de venta ya confirmada.

    Acceso: solo usuarios con role='admin'.

    Validaciones:
      - La venta existe y pertenece al tenant.
      - La venta no pertenece a una caja cerrada (is_closed=True).
      - La venta no está ya anulada (payment_status='cancelled').

    Lógica transaccional (un único commit):
      1. Devuelve stock a BinStock con SELECT FOR UPDATE por item, en orden
         ascendente de product_id para consistencia con process_sale.
      2. Genera StockMovement(reason='anulacion') por cada item revertido.
      3. Genera CashMovement negativo por cada PaymentAllocation con amount>0.
      4. Cancela el AccountReceivable si existe (status='cancelled', balance=0).
      5. Marca Sale.payment_status = 'cancelled'.
    """
    SettingsService.ensure_admin(user)

    sale = session.get(Sale, id)
    if not sale or sale.tenant_id != tenant_id:
        raise HTTPException(404, "Venta no encontrada")
    if sale.is_closed:
        raise HTTPException(400, "No se puede anular una venta perteneciente a una caja ya cerrada")
    if getattr(sale, "payment_status", None) == "cancelled":
        raise HTTPException(400, "La venta ya está anulada")

    from datetime import timezone as _tz

    # ── 1 + 2: Revertir stock por ítem (locks ordenados por product_id) ───────────
    sale_items = session.exec(
        select(SaleItem)
        .where(SaleItem.sale_id == id)
        .order_by(SaleItem.product_id.asc())   # mismo orden que process_sale → evita deadlock
    ).all()

    for item in sale_items:
        # Encontrar el bin de origen: mismo criterio que process_sale
        from database.models import Bin
        target_bin = session.exec(
            select(Bin).where(Bin.tenant_id == tenant_id, Bin.name == "SIN-UBICACION")
        ).first()
        if not target_bin:
            target_bin = session.exec(
                select(Bin).where(Bin.tenant_id == tenant_id, Bin.is_active == True)
            ).first()

        if target_bin:
            # Bloqueo pesimista para evitar race conditions en devolución concurrente
            bin_stock = session.exec(
                select(BinStock)
                .where(
                    BinStock.bin_id == target_bin.id,
                    BinStock.product_id == item.product_id,
                )
                .with_for_update()
            ).first()

            if bin_stock:
                bin_stock.quantity += item.quantity
                bin_stock.updated_at = datetime.now(_tz.utc)
                session.add(bin_stock)
            else:
                # Si no existía el registro (poco probable), lo creamos
                session.add(BinStock(
                    tenant_id=tenant_id,
                    bin_id=target_bin.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                ))

        # Kardex de reversión
        session.add(StockMovement(
            tenant_id=tenant_id,
            product_id=item.product_id,
            from_bin_id=None,
            to_bin_id=target_bin.id if target_bin else None,
            quantity=item.quantity,
            reason="anulacion",
            notes=f"Reversion por anulacion Venta#{id}. Motivo: {reason}",
            user_id=user.id,
        ))

    from decimal import Decimal

    # ── 3: Revertir CashMovements por cada forma de pago ────────────────────────
    allocations = session.exec(
        select(PaymentAllocation).where(PaymentAllocation.sale_id == id)
    ).all()

    for alloc in allocations:
        if (alloc.amount or Decimal("0.00")) <= Decimal("0.00"):
            continue
        method_label = "Efectivo" if alloc.method == "cash" else "Transferencia"
        session.add(CashMovement(
            tenant_id=tenant_id,
            user_id=user.id,
            amount=-alloc.amount,
            movement_type="out",
            concept=f"Anulacion Venta#{id} - {method_label} - Motivo: {reason}",
            reference_type="cancellation",
            reference_id=id,
        ))

    # ── 4: Cancelar AccountReceivable si existe ──────────────────────────────
    ar = session.exec(
        select(AccountReceivable).where(AccountReceivable.sale_id == id)
    ).first()
    if ar:
        ar.status = "cancelled"
        ar.balance = Decimal("0.00")
        session.add(ar)

    # ── 5: Marcar la venta como anulada ───────────────────────────────────
    sale.payment_status = "cancelled"
    session.add(sale)

    # ── Commit único — todo o nada ─────────────────────────────────────────
    session.commit()

    return {
        "ok": True,
        "sale_id": id,
        "reason": reason,
        "items_reverted": len(sale_items),
        "cash_reverted": float(sum((a.amount for a in allocations if (a.amount or Decimal("0.00")) > Decimal("0.00")), Decimal("0.00"))),
        "ar_cancelled": ar is not None,
    }
