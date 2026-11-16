"""
Tipos de cambio.

Fuente real: ExchangeRate-API, endpoint abierto (sin clave), que incluye CLP:
    https://open.er-api.com/v6/latest/USD
Se actualiza aproximadamente una vez al día. Se guarda en caché 6 horas.

Si la API no responde, se usan tasas de respaldo FIJAS y la app lo indica
claramente como "tasas de respaldo, no actualizadas".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests

from servicios import cache

# Monedas disponibles en la interfaz. Para agregar otra, basta con sumarla aquí
# (debe existir en la respuesta de la API).
# "sufijo": el símbolo va después del número (ej. 1.900 €)
MONEDAS = {
    "CLP": {"nombre": "Peso chileno", "simbolo": "$", "decimales": 0},
    "USD": {"nombre": "Dólar estadounidense", "simbolo": "US$", "decimales": 0},
    "EUR": {"nombre": "Euro", "simbolo": "€", "decimales": 0, "sufijo": True},
    "ARS": {"nombre": "Peso argentino", "simbolo": "AR$", "decimales": 0},
    "BRL": {"nombre": "Real brasileño", "simbolo": "R$", "decimales": 0},
    "MXN": {"nombre": "Peso mexicano", "simbolo": "MX$", "decimales": 0},
    "PEN": {"nombre": "Sol peruano", "simbolo": "S/", "decimales": 0},
    "COP": {"nombre": "Peso colombiano", "simbolo": "COL$", "decimales": 0},
    "UYU": {"nombre": "Peso uruguayo", "simbolo": "$U", "decimales": 0},
    "BOB": {"nombre": "Boliviano", "simbolo": "Bs", "decimales": 0},
    "PYG": {"nombre": "Guaraní paraguayo", "simbolo": "₲", "decimales": 0},
    "GBP": {"nombre": "Libra esterlina", "simbolo": "£", "decimales": 0},
    "CHF": {"nombre": "Franco suizo", "simbolo": "CHF ", "decimales": 0},
    "CAD": {"nombre": "Dólar canadiense", "simbolo": "CA$", "decimales": 0},
    "AUD": {"nombre": "Dólar australiano", "simbolo": "AU$", "decimales": 0},
    "JPY": {"nombre": "Yen japonés", "simbolo": "¥", "decimales": 0},
    "CNY": {"nombre": "Yuan chino", "simbolo": "CN¥", "decimales": 0},
    "KRW": {"nombre": "Won surcoreano", "simbolo": "₩", "decimales": 0},
    "INR": {"nombre": "Rupia india", "simbolo": "₹", "decimales": 0},
}

URL_API = "https://open.er-api.com/v6/latest/USD"
URL_API_2 = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"
CABECERAS = {"User-Agent": "GlobeWay/0.1 (python-requests; uso educativo)"}
TTL_SEGUNDOS = 6 * 3600

# Respaldo aproximado. Solo se usa si la API falla y siempre se marca como tal.
TASAS_RESPALDO = {"USD": 1.0, "CLP": 950.0, "EUR": 0.92, "ARS": 1000.0, "BRL": 5.5,
                  "MXN": 18.5, "PEN": 3.7, "COP": 4000.0, "UYU": 40.0, "BOB": 6.9,
                  "PYG": 7500.0, "GBP": 0.78, "CHF": 0.88, "CAD": 1.37, "AUD": 1.5,
                  "JPY": 150.0, "CNY": 7.2, "KRW": 1350.0, "INR": 84.0}
CLAVE_CACHE = "tasas_usd_v2"   # cambió al agregar monedas: no reusar la caché antigua


@dataclass
class Tasas:
    por_usd: dict[str, float]   # cuántas unidades de cada moneda equivalen a 1 USD
    fuente: str
    actualizado: datetime | None
    es_respaldo: bool


def obtener_tasas() -> Tasas:
    en_cache = cache.obtener(CLAVE_CACHE, TTL_SEGUNDOS)
    if en_cache and all(m in en_cache[0] for m in MONEDAS):
        datos, fecha = en_cache
        return Tasas(datos, "ExchangeRate-API (open.er-api.com)", fecha, False)

    errores = []

    # Fuente 1: ExchangeRate-API
    try:
        r = requests.get(URL_API, timeout=10, headers=CABECERAS)
        r.raise_for_status()
        cuerpo = r.json()
        if cuerpo.get("result") != "success":
            raise ValueError(cuerpo.get("error-type", "respuesta inválida"))
        tasas = {m: float(cuerpo["rates"][m]) for m in MONEDAS if m in cuerpo["rates"]}
        fecha = cache.guardar(CLAVE_CACHE, tasas)
        return Tasas(tasas, "ExchangeRate-API (open.er-api.com)", fecha, False)
    except Exception as e:
        errores.append(f"open.er-api.com: {_describir(e)}")

    # Fuente 2 (respaldo con datos reales): currency-api vía jsDelivr
    try:
        r = requests.get(URL_API_2, timeout=10, headers=CABECERAS)
        r.raise_for_status()
        usd = r.json()["usd"]
        tasas = {m: float(usd[m.lower()]) for m in MONEDAS if m.lower() in usd}
        fecha = cache.guardar(CLAVE_CACHE, tasas)
        return Tasas(tasas, "currency-api (jsDelivr)", fecha, False)
    except Exception as e:
        errores.append(f"currency-api: {_describir(e)}")

    return Tasas(dict(TASAS_RESPALDO),
                 "Tasas fijas de respaldo. Motivo: " + " | ".join(errores), None, True)


def _describir(e: Exception) -> str:
    """Traduce el error a algo entendible (en vez de decir siempre 'sin conexión')."""
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return f"el servidor respondió HTTP {e.response.status_code}"
    if isinstance(e, requests.Timeout):
        return "tardó demasiado en responder"
    if isinstance(e, requests.ConnectionError):
        return "no se pudo conectar"
    return e.__class__.__name__


def tasa(moneda: str, tasas: Tasas) -> float:
    """Unidades de la moneda por 1 USD (si la fuente no trae esa moneda, usa la de respaldo)."""
    return tasas.por_usd.get(moneda) or TASAS_RESPALDO.get(moneda, 1.0)


def convertir(monto_usd: float, moneda: str, tasas: Tasas) -> float:
    return monto_usd * tasa(moneda, tasas)


def a_usd(monto: float, moneda: str, tasas: Tasas) -> float:
    return monto / tasa(moneda, tasas)


def formatear(monto: float, moneda: str) -> str:
    info = MONEDAS.get(moneda, {"simbolo": moneda, "decimales": 0})
    texto = f"{monto:,.{info['decimales']}f}"
    # Formato chileno: punto para miles
    texto = texto.replace(",", ".")
    return f"{texto} {info['simbolo']}" if info.get("sufijo") else f"{info['simbolo']}{texto}"
