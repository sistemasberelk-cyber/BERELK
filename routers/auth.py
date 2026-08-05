"""routers/auth.py — Login / Logout"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from database.models import Settings, Tenant, User
from database.session import get_session
from services.auth_service import AuthService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings

router = APIRouter(tags=["Auth"])

def _templates():
    return CompatTemplates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
@router.head("/login")
def login_page(request: Request, settings: Settings = Depends(get_settings)):
    return _templates().TemplateResponse("login.html", {"request": request, "settings": settings})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    user = session.exec(select(User).where(User.username == username)).first()
    
    # 1. Eliminar fallbacks hardcodeados; usar estricta validación por entorno o hash DB
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    is_override = False
    if admin_email and admin_password:
        if username.strip() == admin_email.strip() and password.strip() == admin_password.strip():
            is_override = True

    # 2. Si no existe el usuario pero la credencial maestra de env es correcta, crearlo
    if not user and is_override:
        tenant_id = session.exec(select(Tenant.id).order_by(Tenant.id)).first() or 1
        role = "admin"
        user = User(
            username=username,
            password_hash=AuthService.get_password_hash(password),
            role=role,
            tenant_id=tenant_id,
            is_active=True
        )
        session.add(user)
        session.commit()
        session.refresh(user)


    if not user or (not AuthService.verify_password(password, user.password_hash) and not is_override):
        return _templates().TemplateResponse(
            "login.html", {"request": request, "error": "Credenciales inválidas", "settings": settings}
        )
    request.session["user_id"] = user.id
    if user.role == "superadmin":
        return RedirectResponse("/tenants", status_code=302)
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
