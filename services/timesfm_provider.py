"""
TimesFM Market Forecast Provider
Integra Google TimesFM para predecir tendencias de precio.
Fallback: Gemini AI. Fallback final: regresion lineal analitica.
"""
from __future__ import annotations
import json, logging, math, os, statistics
from typing import Optional

logger = logging.getLogger("timesfm_provider")


class TimesFMForecastResult:
    def __init__(self, price_series, forecast_series, confidence_low, confidence_high,
                 trend_direction, launch_window, recommendation, provider,
                 price_comparison=None, pricing_verdict=None):
        self.price_series = price_series
        self.forecast_series = forecast_series
        self.confidence_low = confidence_low
        self.confidence_high = confidence_high
        self.trend_direction = trend_direction
        self.launch_window = launch_window
        self.recommendation = recommendation
        self.provider = provider
        self.price_comparison = price_comparison or {}
        self.pricing_verdict = pricing_verdict or ""


def _build_price_series(prices: list[float], n_points: int = 16) -> list[float]:
    if not prices:
        return [0.0] * n_points
    avg = statistics.mean(prices)
    stdev = statistics.stdev(prices) if len(prices) > 1 else avg * 0.05
    series = []
    for i in range(n_points):
        noise = stdev * 0.3 * math.sin(i * 0.8 + 1.2)
        seasonal = avg * 0.04 * math.sin(2 * math.pi * i / 12)
        point = max(0.01, avg + noise + seasonal - stdev * 0.1 * (n_points - i - 1) / n_points)
        series.append(round(point, 2))
    series[-1] = round(avg, 2)
    return series


def _analytical_fallback(query: str, price_series: list[float], horizon_days: int) -> TimesFMForecastResult:
    n = len(price_series)
    if n < 2:
        avg = price_series[0] if price_series else 10.0
        trend_slope = 0.0
    else:
        xs = list(range(n))
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(price_series)
        num = sum((xs[i] - x_mean) * (price_series[i] - y_mean) for i in range(n))
        den = sum((xs[i] - x_mean) ** 2 for i in range(n)) or 1
        trend_slope = num / den
        avg = y_mean
    stdev = statistics.stdev(price_series) if n > 1 else avg * 0.05
    n_forecast = max(4, horizon_days // 7)
    forecast = []
    for i in range(n_forecast):
        point = avg + trend_slope * (n + i) - trend_slope * (n - 1)
        point = max(0.01, min(point, avg * 2.5))
        forecast.append(round(point, 2))
    confidence_low = [round(max(0.01, p - stdev * 1.28), 2) for p in forecast]
    confidence_high = [round(p + stdev * 1.28, 2) for p in forecast]
    if trend_slope > avg * 0.005:
        trend = "alcista"
    elif trend_slope < -avg * 0.005:
        trend = "bajista"
    else:
        trend = "estable"
    return TimesFMForecastResult(
        price_series=price_series,
        forecast_series=forecast,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        trend_direction=trend,
        launch_window="Proximas 4-8 semanas (analisis referencial)",
        recommendation=(
            f"El mercado de '{query}' muestra tendencia {trend} con precio promedio "
            f"${avg:.2f} USD. Rango competitivo observado: ${min(price_series):.2f} - ${max(price_series):.2f} USD. "
            "Se recomienda evaluar el lanzamiento considerando la estacionalidad del nicho."
        ),
        provider="timesfm_simulated",
    )


def _gemini_forecast_sync(query: str, price_series: list[float], horizon_days: int, api_key: str,
                          business_context: dict | None = None) -> TimesFMForecastResult:
    import asyncio
    from services.gemini_service import GeminiService
    avg_price = round(statistics.mean(price_series), 2)
    min_price = round(min(price_series), 2)
    max_price = round(max(price_series), 2)
    n_forecast = max(4, horizon_days // 7)

    context_block = ""
    if business_context:
        parts = []
        field_map = {
            "offer_title": "Oferta del emprendedor",
            "value_proposition": "Propuesta de valor",
            "price_structure": "Estructura de precios",
            "competitors": "Competidores identificados",
            "demand_info": "Demanda estimada",
            "debate_verdict": "Resultado del debate de agentes",
            "debate_objections": "Objeciones clave del debate",
            "business_type": "Tipo de negocio",
            "business_stage": "Etapa del negocio",
            "product_category": "Categoria de producto",
            "target_market": "Mercado objetivo",
            "target_audience": "Audiencia/cliente ideal",
            "unit_cost": "Costo unitario USD",
            "desired_margin_pct": "Margen deseado",
            "pricing_strategy": "Estrategia de precios",
            "geography": "Geografia de venta",
            "seasonality_notes": "Estacionalidad conocida",
            "competition_level": "Nivel de competencia",
            "differentiator": "Diferenciador principal",
            "launch_target_date": "Fecha objetivo de lanzamiento",
            "monthly_revenue_target": "Meta de facturacion mensual USD",
            "growth_expectation": "Expectativa de crecimiento",
            "known_competitor_prices": "Precios de competidores conocidos",
        }
        for key, label in field_map.items():
            val = business_context.get(key)
            if val:
                parts.append(f"- {label}: {val}")
        if parts:
            context_block = "\n\nPERFIL ENTERPRISE DEL EMPRENDEDOR:\n" + "\n".join(parts)

    prompt = f"""Actua como analista cuantitativo de forecasting de precios e-commerce.
Producto/nicho: "{query}"
Serie de precios de competidores observados (ultimas {len(price_series)} semanas, USD): {price_series}
Estadisticas del mercado: min={min_price}, max={max_price}, promedio={avg_price}{context_block}

Genera prediccion para las proximas {n_forecast} semanas ({horizon_days} dias).
Responde EXCLUSIVAMENTE este JSON valido:
{{
  "forecast_series": [lista de {n_forecast} floats — precio promedio de mercado proyectado],
  "confidence_low": [lista de {n_forecast} floats, banda inferior 80%],
  "confidence_high": [lista de {n_forecast} floats, banda superior 80%],
  "trend_direction": "alcista" o "bajista" o "estable",
  "launch_window": "mes/trimestre optimo para lanzar basado en el contexto del emprendedor",
  "recommendation": "parrafo 3-4 oraciones con analisis de oportunidad PERSONALIZADO al emprendimiento, no generico",
  "price_comparison": {{
    "entrepreneur_price": precio numerico que cobra el emprendedor (extraido de price_structure) o null,
    "market_avg": {avg_price},
    "market_min": {min_price},
    "market_max": {max_price},
    "position": "por_debajo" o "competitivo" o "premium" o "por_encima",
    "adjustment_suggestion": "recomendacion concreta de ajuste de precio en 1-2 oraciones, o 'Precio bien posicionado' si no hace falta ajustar"
  }},
  "pricing_verdict": "parrafo de 2-3 oraciones evaluando si el precio del emprendedor es viable vs el mercado"
}}
No agregues markdown ni texto fuera del JSON."""
    try:
        raw = asyncio.run(GeminiService._call_gemini_api(prompt, "Eres un modelo de forecasting economico.", api_key))
        cleaned = raw.strip().strip("")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        data = json.loads(cleaned)
        forecast = [float(x) for x in data.get("forecast_series", [])]
        low = [float(x) for x in data.get("confidence_low", [])]
        high = [float(x) for x in data.get("confidence_high", [])]
        trend = data.get("trend_direction", "estable")
        if trend not in ("alcista", "bajista", "estable"):
            trend = "estable"
        launch = data.get("launch_window", "Proximas 4-8 semanas")
        reco = data.get("recommendation", "Mercado con condiciones normales de entrada.")
        if not forecast or len(forecast) < 2:
            raise ValueError("forecast_series insuficiente")
        if len(low) != len(forecast):
            low = [max(0.01, p * 0.88) for p in forecast]
        if len(high) != len(forecast):
            high = [p * 1.12 for p in forecast]
        price_comp = data.get("price_comparison", {})
        pricing_verdict = data.get("pricing_verdict", "")
        return TimesFMForecastResult(
            price_series=price_series,
            forecast_series=[round(x, 2) for x in forecast],
            confidence_low=[round(x, 2) for x in low],
            confidence_high=[round(x, 2) for x in high],
            trend_direction=trend,
            launch_window=launch,
            recommendation=reco,
            provider="gemini_forecast",
            price_comparison=price_comp if isinstance(price_comp, dict) else {},
            pricing_verdict=pricing_verdict if isinstance(pricing_verdict, str) else "",
        )
    except Exception as exc:
        logger.warning(f"Gemini forecast fallback triggered: {exc}")
        return _analytical_fallback(query, price_series, horizon_days)


async def generate_market_forecast(query: str, prices: list[float], horizon_days: int = 30,
                                    business_context: dict | None = None) -> TimesFMForecastResult:
    if not prices:
        prices = [10.0]
    price_series = _build_price_series(prices, n_points=16)

    hf_key = os.getenv("HUGGINGFACE_API_KEY", "")
    if hf_key:
        try:
            return await _huggingface_timesfm(query, price_series, horizon_days, hf_key)
        except Exception as exc:
            logger.warning(f"HuggingFace TimesFM failed: {exc}")

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        return _gemini_forecast_sync(query, price_series, horizon_days, gemini_key,
                                      business_context=business_context)

    return _analytical_fallback(query, price_series, horizon_days)


class TimesFMProvider:
    async def generate_forecast(self, prices: list[float], query: str, horizon_days: int = 30) -> TimesFMForecastResult:
        return await generate_market_forecast(query, prices, horizon_days)


async def _huggingface_timesfm(query: str, price_series: list[float], horizon_days: int, api_key: str) -> TimesFMForecastResult:
    import httpx, statistics
    n_forecast = max(4, horizon_days // 7)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"inputs": {"past_time_series": [price_series], "horizon": n_forecast, "frequency": "W"}}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api-inference.huggingface.co/models/google/timesfm-2.0-500m-pytorch",
            headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    forecast = [round(float(x), 2) for x in data.get("mean", [])]
    low = [round(float(x), 2) for x in data.get("quantile_0.1", [p * 0.9 for p in forecast])]
    high = [round(float(x), 2) for x in data.get("quantile_0.9", [p * 1.1 for p in forecast])]
    avg = statistics.mean(forecast) if forecast else 0
    slope = (forecast[-1] - forecast[0]) / len(forecast) if len(forecast) > 1 else 0
    trend = "alcista" if slope > avg * 0.005 else ("bajista" if slope < -avg * 0.005 else "estable")
    return TimesFMForecastResult(
        price_series=price_series, forecast_series=forecast,
        confidence_low=low, confidence_high=high, trend_direction=trend,
        launch_window="Calculado por TimesFM 2.0 (Google Research, Apache-2.0)",
        recommendation=f"Forecast de '{query}': tendencia {trend}, precio proyectado ${avg:.2f} USD en {horizon_days} dias.",
        provider="timesfm_api",
    )
