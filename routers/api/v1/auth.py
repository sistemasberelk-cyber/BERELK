from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from database.session import get_session
from database.models import User, RefreshToken
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Optional

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    is_onboarded: bool = False

class RefreshRequest(BaseModel):
    refresh_token: str

class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    is_onboarded: bool = False

class LogoutRequest(BaseModel):
    refresh_token: str

@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == req.username)).first()
    
    # 1. Eliminar fallbacks hardcodeados; usar estricta validación por entorno o hash DB
    import os
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    is_override = False
    if admin_email and admin_password:
        if req.username.strip() == admin_email.strip() and req.password.strip() == admin_password.strip():
            is_override = True

    # 2. Crear usuario si no existe pero la clave maestra de env es correcta
    if not user and is_override:
        from database.models import Tenant
        from services.auth_service import AuthService
        tenant_id = session.exec(select(Tenant.id).order_by(Tenant.id)).first() or 1
        role = "admin"
        user = User(
            username=req.username,
            password_hash=AuthService.get_password_hash(req.password),
            role=role,
            tenant_id=tenant_id,
            is_active=True
        )
        session.add(user)
        session.commit()
        session.refresh(user)


    if not user or not user.is_active or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas"
        )
        
    from services.auth_service import AuthService
    if not is_override and not AuthService.verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas"
        )
    
    from services.jwt_service import create_access_token, create_refresh_token, hash_refresh_token
    access = create_access_token(user.id, user.tenant_id, user.role)
    raw_refresh = create_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    
    db_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=refresh_hash,
        expires_at=expires
    )
    session.add(db_token)
    session.commit()
    
    # Fetch is_onboarded from Settings
    from database.models import Settings
    settings = session.exec(select(Settings).where(Settings.tenant_id == user.tenant_id)).first()
    is_onboarded = settings.is_onboarded if settings else False

    return TokenResponse(access_token=access, refresh_token=raw_refresh, is_onboarded=is_onboarded)

@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh(req: RefreshRequest, session: Session = Depends(get_session)):
    from services.jwt_service import hash_refresh_token, create_access_token, create_refresh_token
    r_hash = hash_refresh_token(req.refresh_token)
    db_token = session.exec(select(RefreshToken).where(RefreshToken.token_hash == r_hash)).first()
    if not db_token or db_token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de refresco inválido o revocado"
        )
    
    expires = db_token.expires_at
    if expires.tzinfo is None:
        now = datetime.now()
    else:
        now = datetime.now(timezone.utc)
        
    if expires < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de refresco expirado"
        )
    
    user = session.get(User, db_token.user_id)
    if not user or not user.is_active or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no encontrado"
        )
    
    # 1. Revoke the old refresh token
    db_token.revoked_at = now
    session.add(db_token)
    
    # 2. Generate new tokens
    access = create_access_token(user.id, user.tenant_id, user.role)
    raw_refresh = create_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    
    new_expires = datetime.now(timezone.utc) + timedelta(days=7) if expires.tzinfo is not None else datetime.now() + timedelta(days=7)
    new_db_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=refresh_hash,
        expires_at=new_expires
    )
    session.add(new_db_token)
    session.commit()
    
    # Fetch is_onboarded from Settings
    from database.models import Settings
    settings = session.exec(select(Settings).where(Settings.tenant_id == user.tenant_id)).first()
    is_onboarded = settings.is_onboarded if settings else False

    return RefreshResponse(access_token=access, refresh_token=raw_refresh, is_onboarded=is_onboarded)

@router.post("/auth/logout")
def logout(req: LogoutRequest, session: Session = Depends(get_session)):
    from services.jwt_service import hash_refresh_token
    r_hash = hash_refresh_token(req.refresh_token)
    db_token = session.exec(select(RefreshToken).where(RefreshToken.token_hash == r_hash)).first()
    if db_token:
        db_token.revoked_at = datetime.now(timezone.utc) if db_token.expires_at.tzinfo is not None else datetime.now()
        session.add(db_token)
        session.commit()
    return {"message": "Sesión cerrada correctamente"}
