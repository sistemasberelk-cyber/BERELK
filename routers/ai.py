from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import json
# In a real scenario, you'd use google-genai or google.generativeai here
# For the MVP, we simulate the structure or call the REST API directly
import httpx
from database.session import get_session
from database.models import User
from web.dependencies import get_current_user, get_current_tenant
from services.gemini_service import GeminiService

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
async def generate_copy(req: CopyRequest, db: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key no configurada en el backend.")
    
    # Simple prompt for Gemini 2.5 Flash-Lite
    prompt = f"Genera 3 opciones de copy de ventas persuasivo para el producto '{req.product_name}'. Categoría: {req.category}. Contexto extra: {req.context}. Devuelve solo los textos numerados."
    
    try:
        # Pseudo-code for Gemini REST API call
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return {"success": True, "copies": text.split("\n")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/theme")
async def generate_theme(req: ThemeRequest, db: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
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
            # Limpiar posible texto extra
            text = text.replace('```json', '').replace('```', '').strip()
            theme_json = json.loads(text)
            return {"success": True, "theme": theme_json}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parseando tema: {str(e)}")

@router.get("/onboarding/texts")
async def get_onboarding_texts(step: str, niche: str = "general", db: Session = Depends(get_session)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key no configurada en el backend.")
    try:
        texts = await GeminiService.generate_onboarding_text(step, niche, GEMINI_API_KEY)
        return texts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/image")
async def generate_image(req: ImageRequest, db: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # Simulación de generación de imagen (Gemini Imagen 4 Fast o Vertex AI)
    return {"success": True, "image_url": "https://placehold.co/600x400/png?text=Generated+Image"}

class ProductDescRequest(BaseModel):
    product_name: str
    features: str

@router.post("/product-description")
async def generate_product_description(req: ProductDescRequest, db: Session = Depends(get_session)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key no configurada.")
    try:
        desc = await GeminiService.generate_product_description(req.product_name, req.features, GEMINI_API_KEY)
        return {"success": True, "description": desc}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class LandingCopyRequest(BaseModel):
    niche: str
    audience: str
    tone: str

@router.post("/landing-copy")
async def generate_landing_copy(req: LandingCopyRequest, db: Session = Depends(get_session)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key no configurada.")
    try:
        copy = await GeminiService.generate_landing_copy(req.niche, req.audience, req.tone, GEMINI_API_KEY)
        return {"success": True, "copy": copy}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChatRequest(BaseModel):
    history: list
    new_message: str
    system_instruction: str = "Eres un asistente virtual de ventas amable."

@router.post("/chat")
async def chat_bot_response(req: ChatRequest, db: Session = Depends(get_session)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key no configurada.")
    try:
        response_text = await GeminiService.chat_bot_response(req.history, req.new_message, req.system_instruction, GEMINI_API_KEY)
        return {"success": True, "response": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
