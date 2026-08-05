from __future__ import annotations

from typing import Optional
import os

from fastapi import Depends, HTTPException, Request, status, Header
from sqlmodel import Session, select

from database.models import Tenant, User
from database.session import get_session
from services.settings_service import SettingsService


def _resolve_tenant_from_host(host: str, session: Session) -> Optional[int]:
    """
    If BASE_DOMAIN is set (e.g. "tudominio.com"), resolve tenant by subdomain.
    Example: acme.tudominio.com -> tenant with subdomain "acme".
    """
    base_domain = os.getenv("BASE_DOMAIN")
    if not base_domain:
        return None

    hostname = (host or "").split(":")[0].lower()
    base_domain = base_domain.lower()
    if hostname == base_domain:
        return None
    if not hostname.endswith("." + base_domain):
        return None

    subdomain = hostname.replace("." + base_domain, "")
    tenant = session.exec(select(Tenant).where(Tenant.subdomain == subdomain)).first()
    return tenant.id if tenant else None


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    user = session.get(User, user_id)
    if user and not user.tenant_id:
        tenant = session.exec(select(Tenant).order_by(Tenant.id)).first()
        if tenant:
            user.tenant_id = tenant.id
            session.add(user)
            session.commit()
            session.refresh(user)
    return user


def require_auth(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/login"},
        )
    return user


def get_tenant(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_auth),
) -> int:
    # Resolve tenant by host if configured
    host_tenant_id = _resolve_tenant_from_host(request.headers.get("host"), session)
    if host_tenant_id and user.tenant_id and user.tenant_id != host_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch for this domain")
    if host_tenant_id:
        return host_tenant_id
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated")
    return user.tenant_id


def get_current_tenant(
    request: Request,
    session: Session = Depends(get_session),
) -> int:
    """
    Resolves tenant_id dynamically from session, headers, or subdomains.
    Secured by verification logic to prevent raw/arbitrary client inputs.
    """
    # 1. Try to resolve via active session cookie user
    user_id = request.session.get("user_id")
    if user_id:
        user = session.get(User, user_id)
        if user and user.tenant_id and user.is_active and not user.is_deleted:
            return user.tenant_id

    # 2. Try to resolve via JWT header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            from services.jwt_service import decode_access_token
            payload = decode_access_token(token)
            jwt_user_id = int(payload.get("sub"))
            jwt_user = session.get(User, jwt_user_id)
            if jwt_user and jwt_user.tenant_id and jwt_user.is_active and not jwt_user.is_deleted:
                return jwt_user.tenant_id
        except Exception:
            pass

    # 3. Try to resolve via host subdomain (valid for multi-tenant domains)
    host_tenant_id = _resolve_tenant_from_host(request.headers.get("host"), session)
    if host_tenant_id:
        host_tenant = session.get(Tenant, host_tenant_id)
        if host_tenant and host_tenant.is_active:
            return host_tenant.id

    # Strict check: in production environment, do NOT allow fallback or unauthenticated header overrides
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    if is_production:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida para resolver el tenant en producción"
        )

    # Fallback to the first active tenant ONLY in development environment
    fallback_tenant = session.exec(select(Tenant).order_by(Tenant.id)).first()
    if fallback_tenant and fallback_tenant.is_active:
        return fallback_tenant.id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Active tenant could not be resolved or verified for this session"
    )



def require_superadmin(user: User = Depends(require_auth)) -> User:
    if not user or user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado. Se requiere rol superadmin.")
    return user



def get_settings(
    request: Request,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(get_current_user),
):
    tenant_id = user.tenant_id if user else None
    if tenant_id is None:
        host_tenant = _resolve_tenant_from_host(request.headers.get("host"), session)
        tenant_id = host_tenant if host_tenant else None
    return SettingsService.get_or_create_settings(session, tenant_id=tenant_id)


def get_current_user_jwt(
    authorization: str = Header(...),
    session: Session = Depends(get_session),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token scheme",
        )
    token = authorization.split(" ")[1]
    from services.jwt_service import decode_access_token
    try:
        payload = decode_access_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    
    user_id = int(payload.get("sub"))
    user = session.get(User, user_id)
    if not user or not user.is_active or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def require_roles(allowed_roles: list[str]):
    def dependency(user: User = Depends(get_current_user_jwt)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes. Se requiere rol: {', '.join(allowed_roles)}",
            )
        return user
    return dependency

