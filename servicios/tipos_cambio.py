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
MONEDAS = {
    "CLP": {"nombre": "Peso chileno", "simbolo": "$", "decimales": 0},
    "USD": {"nombre": "Dólar estadounidense", "simbolo": "US$", "decimales": 0},
    "EUR": {"nombre": "Euro", "simbolo": "€", "decimales": 0},
}

URL_API = "https://open.er-api.com/v6/latest/USD"
URL_API_2 = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"
CABECERAS = {"User-Agent": "GlobeWay/0.1 (python-requests; uso educativo)"}
TTL_SEGUNDOS = 6 * 3600

# Respaldo aproximado. Solo se usa si la API falla y siempre se marca como tal.
TASAS_RESPALDO = {"USD": 1.0, "CLP": 950.0, "EUR": 0.92}


@dataclass
class Tasas:
    por_usd: dict[str, float]   # cuántas unidades de cada moneda equivalen a 1 USD
    fuente: str
    actualizado: datetime | None
    es_respaldo: bool


def obtener_tasas() -> Tasas:
    en_cache = cache.obtener("tasas_usd", TTL_SEGUNDOS)
    if en_cache:
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
        fecha = cache.guardar("tasas_usd", tasas)
        return Tasas(tasas, "ExchangeRate-API (open.er-api.com)", fecha, False)
    except Exception as e:
        errores.append(f"open.er-api.com: {_describir(e)}")

    # Fuente 2 (respaldo con datos reales): currency-api vía jsDelivr
    try:
        r = requests.get(URL_API_2, timeout=10, headers=CABECERAS)
        r.raise_for_status()
        usd = r.json()["usd"]
        tasas = {m: float(usd[m.lower()]) for m in MONEDAS if m.lower() in usd}
        fecha = cache.guardar("tasas_usd", tasas)
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


def convertir(monto_usd: float, moneda: str, tasas: Tasas) -> float:
    return monto_usd * tasas.por_usd.get(moneda, 1.0)


def a_usd(monto: float, moneda: str, tasas: Tasas) -> float:
    return monto / tasas.por_usd.get(moneda, 1.0)


def formatear(monto: float, moneda: str) -> str:
    info = MONEDAS.get(moneda, {"simbolo": moneda, "decimales": 0})
    texto = f"{monto:,.{info['decimales']}f}"
    # Formato chileno: punto para miles
    texto = texto.replace(",", ".")
    return f"{info['simbolo']}{texto}" if moneda != "EUR" else f"{texto} €"
