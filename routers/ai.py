from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import json
# In a real scenario, you'd use google-genai or google.generativeai here
# For the MVP, we simulate the structure or call the REST API directly
import httpx
from database.session import get_session
from database.models import User, Tenant
from web.dependencies import get_current_user, get_current_tenant, require_auth
from services.gemini_service import GeminiService
import re, logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI Services"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

class CopyRequest(BaseModel):
    product_name: str
    category: Optional[str] = None
    context: Optional[str] = None

class ThemeRequest(BaseModel):
    description: str

class ImageRequest(BaseModel):
    prompt: str

@router.post("/copy")
async def generate_copy(req: CopyRequest, db: Session = Depends(get_session), current_user: User = Depends(require_auth)):
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key no configurada en el backend.")
    
    prompt = f"Genera 3 opciones de copy de ventas persuasivo para el producto '{req.product_name}'. Categoría: {req.category}. Contexto extra: {req.context}. Devuelve solo los textos numerados."
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return {"success": True, "copies": text.split("\n")}
    except Exception as e:
        logger.error(f"Error generando copy: {e}")
        raise HTTPException(status_code=500, detail="Error interno al generar copy de ventas.")

@router.post("/theme")
async def generate_theme(req: ThemeRequest, db: Session = Depends(get_session), current_user: User = Depends(require_auth)):
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key no configurada.")
    
    prompt = f"""Crea una paleta de colores para una tienda online descrita como: '{req.description}'.
    Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta (reemplazando los hex por los sugeridos):
    {{
      "bg": "#ffffff",
      "primary": "#000000",
      "secondary": "#cccccc",
      "cardBg": "#f0f0f0",
      "border": "#dddddd",
      "text": "#333333",
      "shadow": "0 4px 6px rgba(0,0,0,0.1)"
    }}
    No agregues markdown, ni backticks, ni comentarios."""
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json"}}
            )
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            text = text.replace('```json', '').replace('```', '').strip()
            theme_json = json.loads(text)
            return {"success": True, "theme": theme_json}
    except Exception as e:
        logger.error(f"Error generando tema: {e}")
        raise HTTPException(status_code=500, detail="Error interno al generar paleta de colores.")


import logging
logger = logging.getLogger(__name__)

# Basic in-memory rate limiting for AI calls per tenant
_AI_CALL_LOGS: Dict[int, list] = {}

def _check_ai_rate_limit(tenant_id: int):
    import time
    limit = int(os.getenv("AI_RATE_LIMIT_PER_HOUR", "20"))
    now = time.time()
    cutoff = now - 3600
    
    tenant_calls = _AI_CALL_LOGS.get(tenant_id, [])
    # Filter calls in last hour
    recent_calls = [t for t in tenant_calls if t > cutoff]
    
    if len(recent_calls) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Límite de cuota de IA alcanzado ({limit} peticiones/hora)."
        )
    
    recent_calls.append(now)
    _AI_CALL_LOGS[tenant_id] = recent_calls

@router.get("/onboarding/texts")
async def get_onboarding_texts(
    step: str,
    niche: str = "general",
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Servicio de IA no configurado.")
    try:
        texts = await GeminiService.generate_onboarding_text(step, niche, GEMINI_API_KEY)
        return texts
    except Exception as e:
        logger.error(f"Error en AI onboarding/texts: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")

@router.post("/image")
async def generate_image(req: ImageRequest, db: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)
    return {"success": True, "image_url": "https://placehold.co/600x400/png?text=Generated+Image"}

class ProductDescRequest(BaseModel):
    product_name: str
    features: str

@router.post("/product-description")
async def generate_product_description(
    req: ProductDescRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Servicio de IA no configurado.")
    try:
        desc = await GeminiService.generate_product_description(req.product_name, req.features, GEMINI_API_KEY)
        return {"success": True, "description": desc}
    except Exception as e:
        logger.error(f"Error en AI product-description: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")

class LandingCopyRequest(BaseModel):
    niche: str
    audience: str
    tone: str

@router.post("/landing-copy")
async def generate_landing_copy(
    req: LandingCopyRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Servicio de IA no configurado.")
    try:
        copy = await GeminiService.generate_landing_copy(req.niche, req.audience, req.tone, GEMINI_API_KEY)
        return {"success": True, "copy": copy}
    except Exception as e:
        logger.error(f"Error en AI landing-copy: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")

class ChatRequest(BaseModel):
    history: list
    new_message: str
    system_instruction: str = "Eres un asistente virtual de ventas amable."

@router.post("/chat")
async def chat_bot_response(
    req: ChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Servicio de IA no configurado.")
    try:
        response_text = await GeminiService.chat_bot_response(req.history, req.new_message, req.system_instruction, GEMINI_API_KEY)
        return {"success": True, "response": response_text}
    except Exception as e:
        logger.error(f"Error en AI chat: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")


@router.post("/alex-io")
async def alex_io_chat(
    req: ChatRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant)
):
    from services.ai_brain_service import ai_brain_service
    try:
        response_text = await ai_brain_service.chat_response(
            session=db,
            tenant_id=tenant_id,
            history=req.history,
            new_message=req.new_message,
            system_instruction=req.system_instruction
        )
        return {"success": True, "response": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UIConfigTheme(BaseModel):
    primary_color: str
    secondary_color: str
    mode: str
    background_gradient: Optional[str] = None
    border_radius: Optional[str] = "8px"
    font_family: Optional[str] = "Outfit"

class TemplateStudioRequest(BaseModel):
    prompt: str
    page_name: str = "storefront_home"

def sanitize_css_property(value: str) -> str:
    """
    Sanitizes CSS properties to block stored XSS and malformed styles.
    Blocks url(), expression(), javascript:, script tags, etc.
    """
    if not value:
        return ""
    lower_val = value.lower()
    unsafe_patterns = [
        r"url\s*\(",
        r"expression\s*\(",
        r"javascript\s*:",
        r"<script",
        r"onload",
        r"onerror",
        r"import\s+",
    ]
    for pattern in unsafe_patterns:
        if re.search(pattern, lower_val):
            raise ValueError(f"Estilo CSS no seguro detectado: {value}")
    sanitized = re.sub(r"[^\w\s\d#\(\)%\-,\.\x27\x22:/]", "", value)
    return sanitized

@router.post("/template-studio")
async def ai_template_studio(
    req: TemplateStudioRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant)
):
    from services.ai_brain_service import ai_brain_service
    from database.models import UIConfig
    
    current_config = db.exec(
        select(UIConfig).where(UIConfig.tenant_id == tenant_id, UIConfig.page_name == req.page_name)
    ).first()
    
    current_context = ""
    if current_config:
        current_context = f"Configuración actual: {current_config.theme_json}"
        
    system_instruction = (
        "Eres un diseñador web experto. Tu tarea es generar una paleta de colores y estilos en formato JSON. "
        "Debes responder ÚNICAMENTE con un objeto JSON válido que cumpla este esquema:\n"
        "{\n"
        "  \"primary_color\": \"#HexColor\",\n"
        "  \"secondary_color\": \"#HexColor\",\n"
        "  \"mode\": \"light\" o \"dark\",\n"
        "  \"background_gradient\": \"linear-gradient(to right, #Hex1, #Hex2)\",\n"
        "  \"border_radius\": \"8px\" o similar,\n"
        "  \"font_family\": \"Outfit\" o \"Inter\" o \"Roboto\" o \"Space Grotesk\" o \"DM Sans\"\n"
        "}\n"
        "No agregues markdown ni explicaciones adicionales, solo el JSON estructurado."
    )
    
    prompt = f"Instrucción del usuario: {req.prompt}\n{current_context}"
    
    try:
        response_text = await ai_brain_service.chat_response(
            session=db,
            tenant_id=tenant_id,
            history=[],
            new_message=prompt,
            system_instruction=system_instruction,
            model_name="gemini-3.1-pro"
        )
        
        clean_json_str = response_text.replace("```json", "").replace("```", "").strip()
        theme_dict = json.loads(clean_json_str)
        validated_theme = UIConfigTheme(**theme_dict)
        
        sanitized_theme = {
            "primary_color": sanitize_css_property(validated_theme.primary_color),
            "secondary_color": sanitize_css_property(validated_theme.secondary_color),
            "mode": validated_theme.mode if validated_theme.mode in ["light", "dark"] else "dark",
            "background_gradient": sanitize_css_property(validated_theme.background_gradient or ""),
            "border_radius": sanitize_css_property(validated_theme.border_radius or "8px"),
            "font_family": validated_theme.font_family if validated_theme.font_family in ["Outfit", "Inter", "Roboto", "Space Grotesk", "DM Sans"] else "Outfit"
        }
        
        if not current_config:
            current_config = UIConfig(
                tenant_id=tenant_id,
                page_name=req.page_name,
                layout_json=json.dumps({"modules": ["Header", "StorefrontHero", "StorefrontCatalog", "Footer"]}),
                theme_json=json.dumps(sanitized_theme)
            )
        else:
            current_config.theme_json = json.dumps(sanitized_theme)
            current_config.updated_at = datetime.utcnow()
            
        db.add(current_config)
        db.commit()
        
        return {
            "success": True,
            "theme": sanitized_theme
        }
        
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=f"Validación o límites fallidos: {val_err}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Template Studio: {str(e)}")

@router.get("/credits")
async def get_tenant_credits(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant)
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")
    return {
        "success": True,
        "ai_tier": tenant.ai_tier,
        "ai_credits": tenant.ai_credits
    }

@router.post("/credits/buy")
async def buy_tenant_credits(
    amount: int = 100,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant)
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")
    
    tenant.ai_credits += amount
    db.add(tenant)
    db.commit()
    
    return {
        "success": True,
        "message": f"Se agregaron {amount} créditos con éxito.",
        "ai_credits": tenant.ai_credits
    }
