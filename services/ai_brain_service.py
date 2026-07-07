import httpx
import json
import logging
import os
from datetime import datetime
from sqlmodel import Session, select
from sqlalchemy import func
from database.models import Product, Sale, Tenant, User

logger = logging.getLogger("ai_brain")

class AIBrainService:
    @staticmethod
    def _get_api_key(session: Session, tenant_id: int) -> str:
        """Resolves the Gemini API key for this tenant or falls back to the env variable."""
        # For Fase 2, we fallback to env variable or try decoding AICredential
        env_key = os.getenv("GEMINI_API_KEY", "")
        if env_key:
            return env_key
        return ""

    @staticmethod
    async def _execute_tool(session: Session, tenant_id: int, name: str, args: dict) -> dict:
        """
        Executes the requested tool, strictly injecting tenant_id from the backend session context.
        Regla 1.1: tenant_id never comes from the LLM parameters.
        """
        logger.info(f"🛠&ufe0f Executing tool '{name}' for tenant {tenant_id} with args: {args}")
        try:
            if name == "consultar_stock":
                product_id = args.get("product_id")
                if not product_id:
                    return {"error": "Missing product_id"}
                
                # Verify product belongs to tenant
                product = session.exec(
                    select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
                ).first()
                if not product:
                    return {"error": "Product not found or access denied"}
                
                from database.models import BinStock
                total_stock = session.exec(
                    select(func.sum(BinStock.quantity)).where(
                        BinStock.product_id == product_id, BinStock.tenant_id == tenant_id
                    )
                ).one() or 0
                return {
                    "product_id": product_id,
                    "name": product.name,
                    "total_stock": total_stock
                }

            elif name == "recomendar_productos":
                categoria = args.get("categoria")
                if not categoria:
                    return {"error": "Missing category (categoria)"}
                
                products = session.exec(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.category == categoria,
                        Product.is_deleted == False
                    ).limit(5)
                ).all()
                return {
                    "categoria": categoria,
                    "products": [{"id": p.id, "name": p.name, "price": p.price, "barcode": p.barcode} for p in products]
                }

            elif name == "obtener_metricas_ventas":
                fecha_str = args.get("fecha")
                if not fecha_str:
                    return {"error": "Missing date (fecha) in YYYY-MM-DD format"}
                
                try:
                    target_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                except ValueError:
                    return {"error": "Invalid date format. Use YYYY-MM-DD"}
                
                # Sum total sales on target_date for tenant_id
                sales = session.exec(
                    select(Sale).where(
                        Sale.tenant_id == tenant_id
                    )
                ).all()
                
                day_sales = [s for s in sales if s.timestamp.date() == target_date]
                total_amount = sum(s.total_amount for s in day_sales)
                count = len(day_sales)
                
                return {
                    "date": fecha_str,
                    "total_sales_amount": total_amount,
                    "sales_count": count
                }

            else:
                return {"error": f"Tool '{name}' is not supported"}
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}")
            return {"error": str(e)}

    @classmethod
    async def chat_response(
        cls,
        session: Session,
        tenant_id: int,
        history: list,
        new_message: str,
        system_instruction: str = "Eres un asistente virtual de ventas amable.",
        model_name: str = "gemini-3.5-flash"
    ) -> str:
        """
        Processes a chat conversation turn with Gemini using cascading model.
        Supports multi-turn tool calling with secure backend-injected tenant_id.
        Deducts credits based on model used.
        """
        # Validate model cascade
        allowed_models = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.1-pro"]
        if model_name not in allowed_models:
            model_name = "gemini-3.5-flash"

        # Check tenant credits
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant no encontrado.")

        # Cost config: Pro is 10 credits, others are 1
        cost = 10 if model_name == "gemini-3.1-pro" else 1

        if tenant.ai_credits < cost:
            raise ValueError(f"Créditos de IA insuficientes. Requiere {cost}, disponible {tenant.ai_credits}")

        api_key = cls._get_api_key(session, tenant_id)
        if not api_key:
            raise ValueError("GEMINI_API_KEY no configurada.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        # Define tools schema (Regla 1.1: tenant_id is excluded from declarations)
        tools = [
            {
                "functionDeclarations": [
                    {
                        "name": "consultar_stock",
                        "description": "Obtiene la cantidad total de stock disponible en inventario para un producto específico por su ID.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "product_id": {
                                    "type": "INTEGER",
                                    "description": "ID numérico del producto a consultar."
                                }
                            },
                            "required": ["product_id"]
                        }
                    },
                    {
                        "name": "recomendar_productos",
                        "description": "Recomienda y lista productos activos que correspondan a una categoría específica.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "categoria": {
                                    "type": "STRING",
                                    "description": "Nombre de la categoría de productos (ej. 'Bebidas', 'Indumentaria')."
                                }
                            },
                            "required": ["categoria"]
                        }
                    },
                    {
                        "name": "obtener_metricas_ventas",
                        "description": "Obtiene la suma total facturada y cantidad de ventas registradas en un día específico.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "fecha": {
                                    "type": "STRING",
                                    "description": "Fecha a consultar en formato estricto YYYY-MM-DD."
                                }
                            },
                            "required": ["fecha"]
                        }
                    }
                ]
            }
        ]

        # Prepare messages format for Gemini
        formatted_contents = []
        for turn in history:
            role = "user" if turn.get("role") == "user" else "model"
            formatted_contents.append({
                "role": role,
                "parts": [{"text": turn.get("parts", [{}])[0].get("text", "")}]
            })

        formatted_contents.append({
            "role": "user",
            "parts": [{"text": new_message}]
        })

        async with httpx.AsyncClient() as client:
            # Multi-turn tool execution loop (max 5 turns)
            for _ in range(5):
                payload = {
                    "contents": formatted_contents,
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "tools": tools
                }

                logger.info(f"🤖 Sending request to Gemini ({model_name})...")
                response = await client.post(url, json=payload, timeout=30.0)
                if response.status_code != 200:
                    logger.error(f"Gemini error response: {response.text}")
                    raise ValueError(f"Error de Gemini API: {response.status_code}")

                res_data = response.json()
                candidates = res_data.get("candidates", [])
                if not candidates:
                    raise ValueError("No candidates returned from Gemini API")

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    raise ValueError("Empty response parts from Gemini")

                part = parts[0]
                
                # Check if model requested a function call
                if "functionCall" in part:
                    fn_call = part["functionCall"]
                    fn_name = fn_call["name"]
                    fn_args = fn_call.get("args", {})

                    # Execute the tool with backend-injected tenant_id
                    tool_result = await cls._execute_tool(session, tenant_id, fn_name, fn_args)

                    # Add model's functionCall part to history
                    formatted_contents.append({
                        "role": "model",
                        "parts": [part]
                    })

                    # Add functionResponse part to history (Gemini format)
                    formatted_contents.append({
                        "role": "tool",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": fn_name,
                                    "response": {"output": tool_result}
                                }
                            }
                        ]
                    })
                    # Continue loop to send tool results back to Gemini
                    continue
                else:
                    # Model returned a standard text response
                    tenant.ai_credits -= cost
                    session.add(tenant)
                    session.commit()
                    return part.get("text", "")

        raise ValueError("Excedido el límite máximo de llamadas a herramientas en un solo turno.")

# Singleton instance
ai_brain_service = AIBrainService()
