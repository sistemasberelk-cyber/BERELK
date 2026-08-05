"""routers/clients.py — Clientes + Cuenta Corriente"""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, func, select
from database.models import AccountReceivable, Client, Payment, Sale, Settings, User
from database.session import get_session
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth
from web.pagination import paginate

router = APIRouter(tags=["Clients"])

def _templates():
    return CompatTemplates(directory="templates")

@router.get("/clients", response_class=HTMLResponse)
def get_clients_page(
    request: Request, 
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user: User = Depends(require_auth), 
    settings: Settings = Depends(get_settings), 
    tenant_id: int = Depends(get_tenant), 
    session: Session = Depends(get_session)
):
    query = select(Client).where(Client.tenant_id == tenant_id, Client.is_deleted == False).order_by(Client.name)
    clients_page = paginate(session, query, page=page, size=size)

    # F3-9c: use SUM(AccountReceivable.balance) as source of truth for outstanding debt.
    # This avoids mixing cash sales into the credit balance calculation.
    balances: dict[int, float] = {}
    for c in clients_page.items:
        ar_balance = session.exec(
            select(func.sum(AccountReceivable.balance)).where(
                AccountReceivable.client_id == c.id,
                AccountReceivable.status.in_(["pending", "partial"]),
            )
        ).one() or 0.0
        balances[c.id] = round(ar_balance, 2)
    
    return _templates().TemplateResponse("clients.html", {
        "request": request, 
        "active_page": "clients", 
        "settings": settings, 
        "user": user, 
        "clients": clients_page.items,
        "total": clients_page.total,
        "current_page": clients_page.page,
        "total_pages": clients_page.pages,
        "balances": balances
    })

@router.get("/clients/{id}/account", response_class=HTMLResponse)
def get_client_account(id: int, request: Request, user: User = Depends(require_auth), settings: Settings = Depends(get_settings), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session)):
    client = session.get(Client, id)
    if not client or client.tenant_id != tenant_id:
        raise HTTPException(404, "Client not found")

    sales = session.exec(select(Sale).where(Sale.client_id == id, Sale.tenant_id == tenant_id)).all()
    payments_list = session.exec(select(Payment).where(Payment.client_id == id, Payment.tenant_id == tenant_id)).all()

    from decimal import Decimal

    # F3-9c: balance is the sum of open AccountReceivable.balance — exact outstanding debt.
    # Fallback to the old heuristic for clients who predate the AR migration.
    ar_total_balance = session.exec(
        select(func.sum(AccountReceivable.balance)).where(
            AccountReceivable.client_id == id,
            AccountReceivable.status.in_(["pending", "partial"]),
        )
    ).one() or None

    if ar_total_balance is not None:
        balance = Decimal(str(ar_total_balance))
    else:
        # Legacy fallback: client existed before AR tracking was introduced
        total_debt = sum((Decimal(str(s.total_amount)) if s.total_amount else Decimal("0.00")) for s in sales if (s.amount_paid or Decimal("0.00")) < (s.total_amount or Decimal("0.00")))
        total_paid = sum((Decimal(str(p.amount)) if p.amount else Decimal("0.00")) for p in payments_list)
        balance = max(total_debt - total_paid, Decimal("0.00"))

    movements = []

    def _sort_date(dt_value):
        if dt_value is None: return datetime.min.replace(tzinfo=timezone.utc)
        if isinstance(dt_value, date) and not isinstance(dt_value, datetime):
            dt_value = datetime.combine(dt_value, datetime.min.time())
        if getattr(dt_value, "tzinfo", None) is None:
            return dt_value.replace(tzinfo=timezone.utc)
        return dt_value

    # Process Sales as groups
    for s in sales:
        invoice_num = f"FAC-{s.id}"
        items_desc = ", ".join([f"{it.product_name} (x{it.quantity})" for it in s.items[:3]])
        if len(s.items) > 3: items_desc += "..."
        
        tot_amt = Decimal(str(s.total_amount)) if s.total_amount else Decimal("0.00")
        amt_pd = Decimal(str(s.amount_paid)) if s.amount_paid else Decimal("0.00")
        pending_invoice = tot_amt - amt_pd
        
        movements.append({
            "date": s.timestamp,
            "invoice": invoice_num,
            "type": "Venta",
            "description": items_desc,
            "debit": tot_amt,
            "credit": amt_pd,
            "pending": pending_invoice
        })

    # Process direct payments
    for p in payments_list:
        p_amt = Decimal(str(p.amount)) if p.amount else Decimal("0.00")
        movements.append({
            "date": p.date,
            "invoice": "-",
            "type": "Abono",
            "description": p.note or "Abono a cuenta corriente",
            "debit": Decimal("0.00"),
            "credit": p_amt,
            "pending": None
        })

    movements.sort(key=lambda x: _sort_date(x.get("date")))

    current_balance = Decimal("0.00")
    for m in movements:
        current_balance += m["debit"] or Decimal("0.00")
        current_balance -= m["credit"] or Decimal("0.00")
        m["running_balance"] = current_balance

    return _templates().TemplateResponse("client_account.html", {
        "request": request,
        "active_page": "clients",
        "settings": settings,
        "user": user,
        "client": client,
        "balance": balance,
        "movements": movements
    })

@router.post("/api/clients/{id}/pay")
def register_payment(
    id: int,
    amount: float = Form(...),
    note: Optional[str] = Form(None),
    method: str = Form("cash"),
    session: Session = Depends(get_session),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
):
    from decimal import Decimal
    client = session.get(Client, id)
    if not client or client.tenant_id != tenant_id:
        raise HTTPException(404, "Client not found")
    
    dec_amount = Decimal(str(amount))
    if dec_amount <= Decimal("0.00"):
        raise HTTPException(400, "El monto del pago debe ser mayor a cero")

    open_ars = session.exec(
        select(AccountReceivable)
        .where(
            AccountReceivable.client_id == id,
            AccountReceivable.status.in_(["pending", "partial"]),
        )
        .order_by(AccountReceivable.issued_at.asc())
    ).all()

    remaining = dec_amount
    primary_receivable_id: Optional[int] = None

    for ar in open_ars:
        if remaining <= Decimal("0.00"):
            break

        ar_bal = Decimal(str(ar.balance))
        ar_paid = Decimal(str(ar.paid or "0.00"))
        apply = min(remaining, ar_bal)
        ar.paid = ar_paid + apply
        ar.balance = ar_bal - apply
        remaining = remaining - apply

        if ar.balance <= Decimal("0.00"):
            ar.status = "paid"
            ar.balance = Decimal("0.00")
        else:
            ar.status = "partial"

        session.add(ar)

        if primary_receivable_id is None:
            primary_receivable_id = ar.id

    payment = Payment(
        tenant_id=tenant_id,
        client_id=id,
        amount=dec_amount,
        method=method,
        note=note,
        receivable_id=primary_receivable_id,
    )
    session.add(payment)
    session.commit()
    return RedirectResponse(f"/clients/{id}/account", status_code=303)

@router.get("/api/clients")
def get_clients_api(session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    return session.exec(select(Client).where(Client.tenant_id == tenant_id)).all()

@router.post("/api/clients")
def create_client_api(name: str = Form(...), phone: Optional[str] = Form(None), email: Optional[str] = Form(None), address: Optional[str] = Form(None), credit_limit: Optional[float] = Form(None), razon_social: Optional[str] = Form(None), cuit: Optional[str] = Form(None), iva_category: Optional[str] = Form(None), transport_name: Optional[str] = Form(None), transport_address: Optional[str] = Form(None), session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    client = Client(tenant_id=tenant_id, name=name, phone=phone, email=email, address=address, credit_limit=credit_limit, razon_social=razon_social, cuit=cuit, iva_category=iva_category, transport_name=transport_name, transport_address=transport_address)
    session.add(client)
    session.commit()
    return client

@router.put("/api/clients/{id}")
def update_client_api(id: int, name: str = Form(...), phone: Optional[str] = Form(None), email: Optional[str] = Form(None), address: Optional[str] = Form(None), credit_limit: Optional[float] = Form(None), razon_social: Optional[str] = Form(None), cuit: Optional[str] = Form(None), iva_category: Optional[str] = Form(None), transport_name: Optional[str] = Form(None), transport_address: Optional[str] = Form(None), session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    client = session.get(Client, id)
    if not client or client.tenant_id != tenant_id: raise HTTPException(404, "Not found")
    client.name, client.phone, client.email, client.address = name, phone, email, address
    client.credit_limit, client.razon_social, client.cuit = credit_limit, razon_social, cuit
    client.iva_category, client.transport_name, client.transport_address = iva_category, transport_name, transport_address
    session.add(client)
    session.commit()
    return client

@router.delete("/api/clients/{id}")
def delete_client_api(id: int, session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    client = session.get(Client, id)
    if not client or client.tenant_id != tenant_id: raise HTTPException(404, "Not found")
    client.is_deleted = True
    session.add(client)
    session.commit()
    return {"ok": True}

@router.post("/api/import/clients")
async def import_clients(file: UploadFile = File(...), session: Session = Depends(get_session), user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant)):
    SettingsService.ensure_admin(user)
    import io
    contents = await file.read()
    df = pd.read_excel(io.BytesIO(contents))
    added, errors = 0, []
    for index, row in df.iterrows():
        try:
            name = str(row.get("Name", "")).strip()
            if not name or pd.isna(name): continue
            get_val = lambda col, d=None: str(row.get(col)).strip() if not pd.isna(row.get(col)) else d
            existing = session.exec(select(Client).where(Client.name == name, Client.tenant_id == tenant_id)).first()
            cl = row.get("CreditLimit")
            cl = None if pd.isna(cl) else float(cl)
            if existing:
                for attr, col in [("phone","Phone"),("email","Email"),("address","Address"),("razon_social","RazonSocial"),("cuit","CUIT"),("iva_category","IVACategory"),("transport_name","TransportName"),("transport_address","TransportAddress")]:
                    v = get_val(col)
                    if v: setattr(existing, attr, v)
                if cl is not None: existing.credit_limit = cl
                session.add(existing)
            else:
                session.add(Client(tenant_id=tenant_id, name=name, phone=get_val("Phone"), email=get_val("Email"), address=get_val("Address"), razon_social=get_val("RazonSocial"), cuit=get_val("CUIT"), iva_category=get_val("IVACategory"), credit_limit=cl, transport_name=get_val("TransportName"), transport_address=get_val("TransportAddress")))
                added += 1
        except Exception as e:
            errors.append(f"Row {index}: {e!s}")
    session.commit()
    return {"added": added, "errors": errors}
