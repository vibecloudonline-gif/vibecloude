import logging
import os
from datetime import datetime
from sqlmodel import Session, select
from sqlalchemy import func
from database.models import Product, Sale, Tenant, User

logger = logging.getLogger("ai_brain")


class GeminiUnavailableError(ValueError):
    """Gemini no respondió (sin key, error de API, respuesta vacía/inválida)
    -- distinto de un ValueError de regla de negocio (créditos insuficientes,
    tenant inexistente). Solo este tipo dispara el fallback a Qwen en
    chat_response (Fase 5); las reglas de negocio nunca se saltean con un
    fallback, eso sería un bypass de seguridad, no una alta disponibilidad."""
    pass


class AIBrainService:
    @staticmethod
    def build_dynamic_prompt(session: Session, tenant_id: int) -> str | None:
        from database.models import AlexAgentContext, DebateObjection, Offer, ValidationDebate
        ctx = session.exec(
            select(AlexAgentContext).where(AlexAgentContext.tenant_id == tenant_id)
        ).first()
        if not ctx:
            return None

        parts = []
        tone_map = {
            "profesional_cercano": "profesional pero cercano y amigable",
            "formal": "formal y corporativo",
            "casual": "casual y relajado",
            "tecnico": "tecnico y preciso",
        }
        parts.append(f"Tu tono de comunicacion es {tone_map.get(ctx.personality_tone, ctx.personality_tone)}.")

        if ctx.business_description:
            parts.append(f"El negocio se dedica a: {ctx.business_description}")

        if ctx.validated_offer_id:
            offer = session.exec(
                select(Offer).where(Offer.id == ctx.validated_offer_id, Offer.tenant_id == tenant_id)
            ).first()
            if offer and offer.status == "validated":
                parts.append(
                    f"La oferta validada del negocio es: {offer.title}. "
                    f"Propuesta de valor: {offer.value_proposition}. "
                    f"Precio: {offer.price_structure}."
                )
                if offer.debate and offer.debate.objections:
                    resolved = [
                        o for o in offer.debate.objections
                        if o.resolution_status == "resolved" and o.resolved_text
                    ]
                    if resolved:
                        parts.append("Objeciones resueltas que debes saber responder:")
                        for o in resolved:
                            parts.append(f"- {o.objection_text} -> {o.resolved_text}")

        if ctx.custom_instructions:
            parts.append(f"Instrucciones adicionales del duenio: {ctx.custom_instructions}")

        if ctx.faq_entries_json:
            import json
            try:
                faqs = json.loads(ctx.faq_entries_json)
                if faqs:
                    parts.append("Preguntas frecuentes configuradas:")
                    for faq in faqs:
                        parts.append(f"P: {faq.get('q', '')} R: {faq.get('a', '')}")
            except (json.JSONDecodeError, TypeError):
                pass

        return "\n".join(parts)

    @staticmethod
    def _get_api_key(session: Session, tenant_id: int) -> str:
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
        logger.info(f"Executing tool '{name}' for tenant {tenant_id} with args: {args}")
        try:
            if name == "consultar_stock":
                product_id = args.get("product_id")
                if not product_id:
                    return {"error": "Missing product_id"}

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
        model_name: str = "gemini-3.5-flash",
        allowed_tools: list[str] | None = None,
    ) -> str:
        """
        Punto de entrada público. Intenta Gemini primero; si Gemini no está
        disponible (GeminiUnavailableError), cae a Qwen como fallback de texto
        plano. Errores de negocio NUNCA disparan el fallback.
        """
        try:
            return await cls._chat_response_gemini(
                session, tenant_id, history, new_message, system_instruction, model_name, allowed_tools
            )
        except GeminiUnavailableError as gemini_error:
            from services.ai_gateway_service import ai_gateway_service

            logger.info(f"Gemini no disponible, probando fallback a Qwen: {gemini_error}")
            fallback_text = await ai_gateway_service.chat_fallback_qwen(history, new_message, system_instruction)
            if fallback_text is not None:
                return fallback_text
            raise gemini_error

    @classmethod
    async def _chat_response_gemini(
        cls,
        session: Session,
        tenant_id: int,
        history: list,
        new_message: str,
        system_instruction: str = "Eres un asistente virtual de ventas amable.",
        model_name: str = "gemini-3.5-flash",
        allowed_tools: list[str] | None = None,
    ) -> str:
        """
        Processes a chat conversation turn with Gemini using cascading model.
        Now routes through AI Gateway instead of calling httpx directly.
        """
        from services.ai.contracts import AIError, AIMessage, AIRequest
        from services.ai.gateway import ai_gateway

        allowed_models = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.1-pro"]
        if model_name not in allowed_models:
            model_name = "gemini-3.5-flash"

        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant no encontrado.")

        cost = 10 if model_name == "gemini-3.1-pro" else 1

        if tenant.ai_credits < cost:
            raise ValueError(f"Créditos de IA insuficientes. Requiere {cost}, disponible {tenant.ai_credits}")

        api_key = cls._get_api_key(session, tenant_id)
        if not api_key:
            raise GeminiUnavailableError("GEMINI_API_KEY no configurada.")

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

        if allowed_tools is not None:
            tools[0]["functionDeclarations"] = [
                decl for decl in tools[0]["functionDeclarations"] if decl["name"] in allowed_tools
            ]

        formatted_contents: list[AIMessage] = []
        for turn in history:
            role = "user" if turn.get("role") == "user" else "model"
            formatted_contents.append(AIMessage(
                role=role,
                content=turn.get("parts", [{}])[0].get("text", ""),
            ))

        formatted_contents.append(AIMessage(role="user", content=new_message))

        for _ in range(5):
            request = AIRequest(
                tenant_id=tenant_id,
                task="alex_chat",
                messages=formatted_contents,
                system_prompt=system_instruction,
                model=model_name,
                provider="gemini",
                tools=tools,
                metadata={"api_key": api_key},
                timeout=30.0,
            )

            try:
                response = await ai_gateway.generate(request)
            except AIError as exc:
                raise GeminiUnavailableError(str(exc)) from exc

            if response.tool_calls:
                tc = response.tool_calls[0]
                fn_name = tc["name"]
                fn_args = tc.get("args", {})
                raw_part = tc.get("raw_part", {})

                if allowed_tools is not None and fn_name not in allowed_tools:
                    tool_result = {"error": f"Tool '{fn_name}' no permitida en este contexto"}
                else:
                    tool_result = await cls._execute_tool(session, tenant_id, fn_name, fn_args)

                formatted_contents.append(AIMessage(role="model", parts=[raw_part]))
                formatted_contents.append(AIMessage(
                    role="tool",
                    parts=[{
                        "functionResponse": {
                            "name": fn_name,
                            "response": {"output": tool_result}
                        }
                    }],
                ))
                continue
            else:
                tenant.ai_credits -= cost
                session.add(tenant)
                session.commit()
                return response.content

        raise ValueError("Excedido el límite máximo de llamadas a herramientas en un solo turno.")


ai_brain_service = AIBrainService()
