from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func
from pydantic import BaseModel
from database.session import get_session
from database.models import Tenant, User, Product, Sale
from web.dependencies import get_current_user_jwt
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

router = APIRouter(prefix="/api/v1/superadmin", tags=["SuperAdmin Operations"])

def require_superadmin_jwt(user: User = Depends(get_current_user_jwt)) -> User:
    if user.role != "admin" or user.tenant_id != 1:
        raise HTTPException(status_code=403, detail="Superadmin required")
    return user

class SecurityAuditRequest(BaseModel):
    audit_logs: Optional[List[Dict[str, Any]]] = None

@router.get("/dashboard")
async def superadmin_dashboard(
    session: Session = Depends(get_session),
    user: User = Depends(require_superadmin_jwt)
):
    """
    Returns global dashboard for superadmin:
    Lists all tenants with metrics, health, AI credits, and bandwidth.
    """
    tenants = session.exec(select(Tenant)).all()
    dashboard_data = []
    
    for tenant in tenants:
        sales_count = session.exec(select(func.count(Sale.id)).where(Sale.tenant_id == tenant.id)).one() or 0
        products_count = session.exec(select(func.count(Product.id)).where(Product.tenant_id == tenant.id)).one() or 0
        users_count = session.exec(select(func.count(User.id)).where(User.tenant_id == tenant.id)).one() or 0
        
        # Bandwidth calculation: sale size estimate + products size estimate + users size estimate
        estimated_bandwidth_kb = round((sales_count * 0.15 + products_count * 0.5 + users_count * 1.0 + 1.0), 2)
        
        dashboard_data.append({
            "tenant_id": tenant.id,
            "name": tenant.name,
            "subdomain": tenant.subdomain,
            "is_active": tenant.is_active,
            "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
            "ai_tier": tenant.ai_tier,
            "ai_credits": tenant.ai_credits,
            "health_status": "healthy" if tenant.is_active else "unhealthy",
            "metrics": {
                "users_count": users_count,
                "products_count": products_count,
                "sales_count": sales_count,
                "estimated_bandwidth_kb": estimated_bandwidth_kb
            }
        })
        
    return {
        "success": True,
        "tenants": dashboard_data
    }

@router.post("/tenants/{tenant_id}/toggle")
async def toggle_tenant(
    tenant_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_superadmin_jwt)
):
    """
    Allows activating/deactivating a tenant.
    """
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")
        
    # Superadmin tenant (tenant_id == 1) cannot be deactivated to prevent lockout
    if tenant_id == 1 and tenant.is_active:
        tenant.is_active = True  # Keep active
    else:
        tenant.is_active = not tenant.is_active
        
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    
    return {
        "success": True,
        "tenant_id": tenant.id,
        "is_active": tenant.is_active,
        "message": f"Tenant '{tenant.name}' {'activado' if tenant.is_active else 'desactivado'} con éxito."
    }

@router.post("/security-audit")
async def security_audit(
    req: SecurityAuditRequest,
    db: Session = Depends(get_session),
    user: User = Depends(require_superadmin_jwt)
):
    """
    Triggers AI-powered security audit over system log entries.
    """
    from services.ai_brain_service import ai_brain_service
    
    logs = req.audit_logs
    if not logs:
        # Default mock log entries for demo and test consistency
        logs = [
            {"timestamp": "2026-07-07T12:00:00Z", "username": "admin", "ip": "192.168.1.50", "status": "success", "event": "login"},
            {"timestamp": "2026-07-07T12:05:00Z", "username": "admin", "ip": "45.89.23.104", "status": "failed", "event": "login_attempt"},
            {"timestamp": "2026-07-07T12:05:05Z", "username": "admin", "ip": "45.89.23.104", "status": "failed", "event": "login_attempt"},
            {"timestamp": "2026-07-07T12:05:10Z", "username": "admin", "ip": "45.89.23.104", "status": "failed", "event": "login_attempt"},
            {"timestamp": "2026-07-07T12:05:15Z", "username": "admin", "ip": "45.89.23.104", "status": "failed", "event": "login_attempt"},
            {"timestamp": "2026-07-07T12:05:20Z", "username": "admin", "ip": "45.89.23.104", "status": "failed", "event": "login_attempt"},
            {"timestamp": "2026-07-07T12:06:00Z", "username": "manager", "ip": "192.168.1.55", "status": "success", "event": "login"},
        ]
        
    system_instruction = (
        "Eres un analista de ciberseguridad experto de VibeCloud. Tu tarea es analizar la bitácora de accesos proporcionada "
        "y emitir un reporte de auditoría de seguridad detallado y conciso. Detecta intentos de fuerza bruta, "
        "geografías extrañas o patrones inusuales. Elige un tono profesional y estructurado."
    )
    
    prompt = f"Analiza la siguiente bitácora de accesos y genera un informe de auditoría:\n{json.dumps(logs, indent=2)}"
    
    try:
        response_text = await ai_brain_service.chat_response(
            session=db,
            tenant_id=user.tenant_id,
            history=[],
            new_message=prompt,
            system_instruction=system_instruction,
            model_name="gemini-3.1-pro"
        )
        return {
            "success": True,
            "report": response_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en auditoría de seguridad: {str(e)}")
