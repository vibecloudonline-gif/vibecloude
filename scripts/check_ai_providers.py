"""scripts/check_ai_providers.py — Prueba de conectividad de los 3
proveedores de IA (Claude, Gemini, Qwen) usando las mismas clases y modelos
que ya usa la app en producción (services/ai_gateway_service.py y
services/landing_service.py), no una llamada paralela reinventada.

No pide ni imprime ninguna API key -- las lee de las variables de entorno
ya definidas (o de un .env local vía python-dotenv, igual que hace
database/session.py). Si una variable no está seteada, esa prueba se
reporta como "sin configurar", nunca como fallo.

Uso:
    python scripts/check_ai_providers.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Las respuestas de los proveedores pueden traer acentos -- en la consola de
# Windows (cp1252 por defecto) eso puede romper el print. Forzamos UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"

TEST_SYSTEM_PROMPT = "Sos un chequeo de conectividad. Respondé únicamente con la palabra OK, sin nada más."
TEST_USER_PROMPT = "Respondé con la palabra OK."


def _print_result(name: str, model: str, ok: bool, detail: str, elapsed: float) -> None:
    status = f"{GREEN}[OK]{RESET}" if ok else f"{RED}[FALLO]{RESET}"
    print(f"{BOLD}{name:<8}{RESET} [{model}]  {status}  ({elapsed:.2f}s)")
    print(f"          {detail}")


def _print_skip(name: str, env_var: str) -> None:
    print(f"{BOLD}{name:<8}{RESET} {YELLOW}[SIN CONFIGURAR]{RESET}  ({env_var} no esta seteada)")


async def check_claude() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        _print_skip("Claude", "ANTHROPIC_API_KEY")
        return

    import anthropic
    from services.ai_gateway_service import ANTHROPIC_MODEL

    client = anthropic.AsyncAnthropic(api_key=api_key)
    start = time.monotonic()
    try:
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=10,
            system=TEST_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": TEST_USER_PROMPT}],
        )
        elapsed = time.monotonic() - start
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        _print_result("Claude", ANTHROPIC_MODEL, True, f"Respuesta: {text!r}", elapsed)
    except anthropic.APIError as exc:
        elapsed = time.monotonic() - start
        _print_result("Claude", ANTHROPIC_MODEL, False, str(exc), elapsed)


async def check_gemini() -> None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        _print_skip("Gemini", "GEMINI_API_KEY")
        return

    from services.landing_service import GEMINI_MODEL, _call_gemini

    start = time.monotonic()
    try:
        text = await _call_gemini(TEST_USER_PROMPT, api_key)
        elapsed = time.monotonic() - start
        _print_result("Gemini", GEMINI_MODEL, True, f"Respuesta: {text.strip()!r}", elapsed)
    except Exception as exc:  # noqa: BLE001 - queremos reportar cualquier error del proveedor, no propagarlo
        elapsed = time.monotonic() - start
        _print_result("Gemini", GEMINI_MODEL, False, str(exc), elapsed)


async def check_qwen() -> None:
    api_key = os.getenv("QWEN_API_KEY", "")
    if not api_key:
        _print_skip("Qwen", "QWEN_API_KEY")
        return

    from services.ai_gateway_service import AIGatewayError, QwenClient

    client = QwenClient()
    start = time.monotonic()
    try:
        text = await client.chat(TEST_SYSTEM_PROMPT, TEST_USER_PROMPT)
        elapsed = time.monotonic() - start
        _print_result("Qwen", client.model, True, f"Respuesta: {text.strip()!r}", elapsed)
    except AIGatewayError as exc:
        elapsed = time.monotonic() - start
        _print_result("Qwen", client.model, False, str(exc), elapsed)


async def main() -> None:
    print(f"{BOLD}Chequeo de conectividad — Claude / Gemini / Qwen{RESET}\n")
    await check_claude()
    print()
    await check_gemini()
    print()
    await check_qwen()
    print()


if __name__ == "__main__":
    asyncio.run(main())
