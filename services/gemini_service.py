import os
from datetime import datetime
import httpx
import json
import logging

logger = logging.getLogger(__name__)

class GeminiService:
    @classmethod
    def get_default_seasonal_theme(cls, date_str: str | None = None) -> dict:
        """
        Returns a rich default aesthetic theme adapted to season or month.
        Used as fallback when external Gemini API is unreachable or returns 404/errors.
        """
        month = datetime.now().month
        if month in [12, 1, 2]:
            return {
                "theme": {
                    "primary_color": "#6366f1",
                    "secondary_color": "#a855f7",
                    "mode": "dark",
                    "background_gradient": "linear-gradient(135deg, #0f172a, #1e1b4b)",
                    "border_radius": "0.75rem",
                    "font_family": "Inter"
                }
            }
        elif month in [3, 4, 5]:
            return {
                "theme": {
                    "primary_color": "#f97316",
                    "secondary_color": "#eab308",
                    "mode": "dark",
                    "background_gradient": "linear-gradient(135deg, #1c1917, #292524)",
                    "border_radius": "0.75rem",
                    "font_family": "Outfit"
                }
            }
        elif month in [6, 7, 8]:
            return {
                "theme": {
                    "primary_color": "#0ea5e9",
                    "secondary_color": "#06b6d4",
                    "mode": "dark",
                    "background_gradient": "linear-gradient(135deg, #0b1329, #172554)",
                    "border_radius": "0.75rem",
                    "font_family": "Inter"
                }
            }
        else:
            return {
                "theme": {
                    "primary_color": "#10b981",
                    "secondary_color": "#14b8a6",
                    "mode": "dark",
                    "background_gradient": "linear-gradient(135deg, #064e3b, #022c22)",
                    "border_radius": "0.75rem",
                    "font_family": "Inter"
                }
            }

    @staticmethod
    async def _call_gemini_api(
        prompt: str,
        system_instruction: str,
        api_key: str,
        model: str | None = None,
        force_json: bool = True
    ) -> str:
        """
        Calls Google Gemini API via native HTTP request using httpx.
        Tries preferred model first, with fallback to standard candidate models if 404 occurs.
        """
        preferred = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        candidates = [preferred, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        models_to_try = []
        for m in candidates:
            if m and m not in models_to_try:
                models_to_try.append(m)

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }
        if force_json:
            payload["generationConfig"] = {
                "responseMimeType": "application/json"
            }

        last_error = None
        async with httpx.AsyncClient() as client:
            for current_model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
                try:
                    response = await client.post(url, json=payload, timeout=30.0)
                    if response.status_code == 404:
                        logger.warning(f"Gemini model '{current_model}' returned 404. Attempting candidate fallback...")
                        last_error = ValueError(f"Error de Gemini API: 404 (Model {current_model} not found)")
                        continue
                    if response.status_code != 200:
                        logger.error(f"Gemini API Error ({current_model}): Status {response.status_code}, Body: {response.text[:200]}")
                        raise ValueError(f"Error de Gemini API: {response.status_code}")

                    res_data = response.json()
                    candidates_res = res_data.get("candidates", [])
                    if not candidates_res:
                        raise ValueError("No candidates returned from Gemini API")

                    parts = candidates_res[0].get("content", {}).get("parts", [])
                    if not parts:
                        raise ValueError("No content parts returned from Gemini API")

                    return parts[0].get("text", "")
                except httpx.RequestError as e:
                    logger.error(f"HTTP Request to Gemini failed ({current_model}): {e}")
                    raise ValueError(f"Error de conexión con la API de Gemini: {e}")

        if last_error:
            raise last_error
        raise ValueError("Error de Gemini API: No candidate model succeeded.")

    @classmethod
    async def generate_ui_design(cls, prompt: str, current_layout: dict, current_theme: dict, api_key: str) -> dict:
        """
        Generates layout and theme configurations based on user natural language input.
        """
        system_instruction = """
        Eres un experto diseñador de interfaces y arquitecto frontend de Server-Driven UI (SDUI).
        Tu trabajo es generar un diseño de UI (layout) y tema estético en formato JSON basado en el prompt del usuario y la configuración actual.

        Debes retornar EXCLUSIVAMENTE un objeto JSON con dos llaves principales: "layout" y "theme".

        El catálogo de componentes de presentación disponibles es:
        - "Header": Cabecera con título del POS, información del Tenant y usuario.
        - "ProductSearchBox": Buscador de productos por código de barras o nombre.
        - "CatalogGrid": Grilla de catálogo con paginación y tarjetas de productos.
        - "CartDetail": Detalle del carrito de compras con botones de incremento/decremento.
        - "PaymentSection": Métodos de cobro (efectivo, transferencia, mixto) y botón de cierre de venta.
        - "SalesHistory": Historial de ventas recientes.
        - "Footer": Barra de estado inferior.

        Esquema del JSON de salida esperado:
        {
          "layout": {
            "modules": ["Header", "ProductSearchBox", "CatalogGrid", "CartDetail", "PaymentSection", "Footer"],
            "grid_cols": 12,
            "layout_structure": {
              "Header": {"row": 1, "col_span": 12},
              "ProductSearchBox": {"row": 2, "col_span": 12},
              "CatalogGrid": {"row": 3, "col_span": 8},
              "CartDetail": {"row": 3, "col_span": 4},
              "PaymentSection": {"row": 4, "col_span": 12},
              "Footer": {"row": 5, "col_span": 12}
            }
          },
          "theme": {
            "primary_color": "#HEX",
            "secondary_color": "#HEX",
            "mode": "dark" o "light",
            "background_gradient": "degradado CSS (ej. linear-gradient(135deg, #1e1b4b, #311042))",
            "border_radius": "px o rem",
            "font_family": "fuente de Google Fonts (ej. 'Inter', 'Outfit')"
          }
        }
        """

        user_prompt = f"""
        Configuración actual:
        Layout actual: {json.dumps(current_layout)}
        Tema actual: {json.dumps(current_theme)}

        Prompt del usuario: "{prompt}"

        Genera una interfaz optimizada, estética y premium que se ajuste al prompt. Retorna solo el JSON estructurado.
        """

        result_text = await cls._call_gemini_api(user_prompt, system_instruction, api_key)
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse Gemini output as JSON: {result_text}")
            raise ValueError("La respuesta de Gemini no es un JSON válido.")

    @classmethod
    async def generate_onboarding_text(cls, step: str, niche: str, api_key: str) -> dict:
        ANTIGRAVITY_SYSTEM_PROMPT = """
        Eres la voz oficial de **Antigravity**, una plataforma de tecnología avanzada que combina IA, diseño y automatización para impulsar negocios hacia el futuro.

        Tu estilo es:
        - Futurista y visionario.
        - Energético y motivador.
        - Claro y directo, pero con un toque inspirador.
        - Usas metáforas espaciales, de gravedad, levitación y viajes en el tiempo cuando es apropiado.
        - Evitas lenguaje demasiado técnico; traduces conceptos complejos en beneficios simples.

        Tu objetivo en el onboarding es:
        - Hacer que el usuario se sienta parte de algo grande e innovador.
        - Guiarlo paso a paso con claridad y confianza.
        - Personalizar el mensaje según su nicho y tipo de negocio.

        Responde siempre en español, a menos que se te pida otro idioma.
        DEBES RETORNAR ÚNICAMENTE UN JSON VÁLIDO CON LAS LLAVES: "title", "subtitle", "body". El contenido debe ser HTML limpio (solo <h1>, <h2>, <p>, <strong>).
        """

        if step == "1":
            prompt = f"""
            Genera el texto para la pantalla de **bienvenida** del onboarding.
            Contexto: El usuario acaba de registrarse en Antigravity. Quiere crear su tienda online y sistema de facturación. Nicho: {niche}.
            Tu objetivo es darle la bienvenida y explicarle qué puede lograr.
            Por favor, genera:
            1. Un título principal épico y futurista ("title").
            2. Un subtítulo que resuma qué hará Antigravity por su negocio ("subtitle").
            3. Un párrafo breve que invite a continuar ("body").
            """
        elif step == "2":
            prompt = """
            Genera el texto para la pantalla de **selección de nicho**.
            Contexto: El usuario debe elegir el tipo de negocio.
            Por favor, genera:
            1. Un título que hable de 'elegir el universo de tu negocio' ("title").
            2. Un subtítulo que explique por qué elegir el nicho correcto es importante ("subtitle").
            3. Una descripción corta para que el usuario proceda a seleccionar las opciones abajo ("body").
            """
        elif step == "3":
            prompt = f"""
            Genera el texto para la pantalla de **configuración inicial de la marca**.
            Contexto: El usuario ha elegido el nicho {niche}. Ahora debe poner nombre a su negocio y elegir colores.
            Por favor, genera:
            1. Un título que hable de 'dar vida a tu marca' o 'activar tu identidad' ("title").
            2. Un subtítulo que explique por qué los colores y el logo son clave ("subtitle").
            3. Un texto animando a completar el formulario inferior ("body").
            """
        elif step == "4":
            prompt = f"""
            Genera el texto para la pantalla final del onboarding: **"¡Todo listo!"**.
            Contexto: El usuario de nicho {niche} ya configuró todo. Antigravity ha generado automáticamente su tienda.
            Por favor, genera:
            1. Un título épico, como "Tu negocio acaba de despegar" ("title").
            2. Un subtítulo que resuma lo que ya tiene funcionando ("subtitle").
            3. Una lista HTML (<ul><li>) de 3 logros: Tienda online lista, Sistema de facturación activado, Landing page generada por IA ("body").
            """
        else:
            raise ValueError("Invalid step")

        try:
            result_text = await cls._call_gemini_api(prompt, ANTIGRAVITY_SYSTEM_PROMPT, api_key)
            return json.loads(result_text)
        except Exception as e:
            logger.warning(f"Gemini API rate limited or failed (using robust offline fallback): {e}")
            # Fallback robusto sin emojis y con diseño limpio en base al paso y nicho
            if step == "1":
                return {
                    "title": "Bienvenido a la Facturacion del Futuro",
                    "subtitle": f"Tu portal B2B para {niche} esta despegando.",
                    "body": "<p>Hemos activado tu base de operaciones. Haz clic abajo para iniciar la configuracion del sistema de inventario y canales de venta de manera automatica.</p>"
                }
            elif step == "2":
                return {
                    "title": "Configura tu Universo Comercial",
                    "subtitle": "Selecciona el nicho para adaptar el catalogo y reglas de negocio.",
                    "body": "<p>Cada industria tiene sus propias reglas. Elige la categoria que mejor represente tus productos para habilitar modulos especificos.</p>"
                }
            elif step == "3":
                return {
                    "title": "Identidad de Marca Activa",
                    "subtitle": "Establece los colores de acento para tu Server-Driven UI.",
                    "body": "<p>Define el nombre de tu empresa y el esquema de color. La interfaz de Next.js se adaptara en tiempo real utilizando las variables inyectadas.</p>"
                }
            else:
                return {
                    "title": "Sistema en Orbita y Listo",
                    "subtitle": "Los canales de distribucion han sido sincronizados.",
                    "body": "<ul><li>Catalogo online B2B/B2C publicado.</li><li>Control de stock e idempotencia activado.</li><li>Panel de facturacion listo para operar.</li></ul>"
                }


    @classmethod
    async def generate_daily_theme(cls, date_str: str, api_key: str) -> dict:
        """
        Generates a theme configuration adapted to the date (seasons, events, holidays).
        If external API is unavailable or returns 404, gracefully returns default seasonal theme.
        """
        system_instruction = """
        Eres un diseñador de interfaces creativo y experto en branding y psicología del color.
        Tu trabajo es generar un tema visual estético (colores, gradientes, fuentes, bordes) adaptado a la festividad, estación del año o evento mundial especial de la fecha proporcionada.

        Debes retornar EXCLUSIVAMENTE un objeto JSON con una llave principal "theme":
        {
          "theme": {
            "primary_color": "#HEX",
            "secondary_color": "#HEX",
            "mode": "dark" o "light",
            "background_gradient": "degradado CSS (ej. linear-gradient(135deg, #1e1b4b, #311042))",
            "border_radius": "px o rem",
            "font_family": "fuente de Google Fonts"
          }
        }
        """

        prompt = f"""
        Fecha de hoy: {date_str}

        Analiza si hay eventos importantes (por ejemplo: Mundial de Fútbol, Navidad, Día del Padre, Halloween) o el cambio de estación (Verano, Primavera, Otoño, Invierno) asociado a esta época en general.
        Genera un tema estético premium (colores HSL/Hex, gradientes) que represente esta fecha o época.
        Por ejemplo, si es época del Mundial, usa tonos celestes/blancos o deportivos; si es Navidad, tonos rojos/verdes o invernales dorados; si es verano, colores cálidos y frescos.
        Retorna solo el JSON estructurado.
        """

        try:
            result_text = await cls._call_gemini_api(prompt, system_instruction, api_key)
            parsed = json.loads(result_text)
            if "theme" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Gemini daily theme generation unavailable ({e}). Applying default seasonal theme fallback.")

        return cls.get_default_seasonal_theme(date_str)

    @classmethod
    async def generate_product_description(cls, product_name: str, features: str, api_key: str) -> str:
        """
        Generates a persuasive SEO-optimized product description in HTML.
        """
        system_instruction = "Eres un experto en copywriting para e-commerce."
        prompt = f"""
        Genera una descripción persuasiva, atractiva y optimizada para SEO para el siguiente producto:
        Producto: {product_name}
        Características clave: {features}
        
        Devuelve la descripción en formato HTML limpio (solo etiquetas <p>, <ul>, <li>, <strong>) para insertarlo directo en la web.
        NO devuelvas bloques de código (```html), devuelve directamente el string HTML.
        """

        try:
            text_content = await cls._call_gemini_api(prompt, system_instruction, api_key, force_json=False)
            return text_content.replace('```html', '').replace('```', '').strip()
        except Exception as e:
            logger.error(f"Error calling Gemini for product description: {e}")
            raise ValueError(f"Error de conexión con la API de Gemini: {e}")

    @classmethod
    async def generate_landing_copy(cls, niche: str, audience: str, tone: str, api_key: str) -> dict:
        """
        Generates structured copy for a landing page.
        """
        system_instruction = "Eres un experto creador de Landing Pages y copywriter para marketing digital."
        prompt = f"""
        Crea el texto para una Landing Page de un negocio de: {niche}.
        El público objetivo es: {audience}.
        El tono de la marca debe ser: {tone}.
        
        Debes retornar EXCLUSIVAMENTE un objeto JSON válido con esta estructura exacta:
        {{
            "h1": "Título principal que llame la atención",
            "h2": "Subtítulo que explique el beneficio principal",
            "bullets": ["Dolor que soluciona 1", "Dolor que soluciona 2", "Dolor que soluciona 3"],
            "cta": "Llamado a la acción potente"
        }}
        No agregues markdown ni texto fuera del JSON.
        """
        result_text = await cls._call_gemini_api(prompt, system_instruction, api_key)
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse Gemini landing copy output as JSON: {result_text}")
            raise ValueError("La respuesta de Gemini para Landing Copy no es un JSON válido.")

    @classmethod
    async def chat_bot_response(cls, history: list, new_message: str, system_instruction: str, api_key: str) -> str:
        """
        Handles chatbot multi-turn conversation.
        """
        preferred = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        candidates = [preferred, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        models_to_try = []
        for m in candidates:
            if m and m not in models_to_try:
                models_to_try.append(m)

        contents = history + [{"role": "user", "parts": [{"text": new_message}]}]
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_instruction}]}
        }

        last_error = None
        async with httpx.AsyncClient() as client:
            for current_model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
                try:
                    response = await client.post(url, json=payload, timeout=30.0)
                    if response.status_code == 404:
                        logger.warning(f"Gemini model '{current_model}' returned 404 in chatbot. Retrying next model...")
                        last_error = ValueError(f"Error de Gemini API: 404 (Model {current_model} not found)")
                        continue
                    if response.status_code != 200:
                        raise ValueError(f"Error de Gemini API: {response.status_code}")
                    res_data = response.json()
                    candidates_res = res_data.get("candidates", [])
                    if candidates_res:
                        return candidates_res[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    raise ValueError("No candidates returned from Gemini chatbot API")
                except httpx.RequestError as e:
                    logger.error(f"Error calling Gemini for chatbot ({current_model}): {e}")
                    last_error = ValueError(f"Error de conexión con la API de Gemini chatbot: {e}")

        if last_error:
            raise last_error
        raise ValueError("Error de conexión con la API de Gemini chatbot.")
