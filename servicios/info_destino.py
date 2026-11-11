"""
Información general y fotografía de cada destino desde Wikipedia en español
(API pública, sin clave). Se guarda en caché 7 días.

Wikimedia rechaza (HTTP 403) las solicitudes sin un User-Agent que identifique
la aplicación y un medio de contacto. Se puede definir WIKI_CONTACTO en .env
(una URL o correo tuyo) para cumplir su política.
"""
from __future__ import annotations

import os
from urllib.parse import quote

import requests

from servicios import cache

URL_REST = "https://es.wikipedia.org/api/rest_v1/page/summary/{}"
URL_ACTION = "https://es.wikipedia.org/w/api.php"
TTL = 7 * 24 * 3600


def _cabeceras() -> dict:
    contacto = os.getenv("WIKI_CONTACTO", "https://github.com/globe-travel-demo")
    ua = f"GlobeWay/0.1 ({contacto}) python-requests"
    return {"User-Agent": ua, "Api-User-Agent": ua}


def resumen(titulo: str) -> dict:
    """
    Devuelve {'extracto', 'imagen', 'url', 'error'}.
    'error' es None si todo salió bien, o un texto que explica el motivo real.
    Solo se guardan en caché los resultados exitosos.
    """
    clave = f"wiki:{titulo}"
    en_cache = cache.obtener(clave, TTL)
    if en_cache:
        return en_cache[0]

    errores = []

    # Intento 1: API REST (resumen + imagen principal)
    try:
        r = requests.get(URL_REST.format(quote(titulo.replace(" ", "_"))),
                         headers=_cabeceras(), timeout=10)
        r.raise_for_status()
        d = r.json()
        datos = {
            "extracto": d.get("extract", ""),
            "imagen": (d.get("originalimage") or d.get("thumbnail") or {}).get("source"),
            "url": d.get("content_urls", {}).get("desktop", {}).get("page"),
            "error": None,
        }
        cache.guardar(clave, datos)
        return datos
    except Exception as e:
        errores.append(_describir(e))

    # Intento 2: API clásica (otro punto de acceso de Wikipedia)
    try:
        r = requests.get(URL_ACTION, headers=_cabeceras(), timeout=10, params={
            "action": "query", "format": "json", "redirects": 1, "titles": titulo,
            "prop": "extracts|pageimages|info", "exintro": 1, "explaintext": 1,
            "piprop": "original", "inprop": "url",
        })
        r.raise_for_status()
        pagina = next(iter(r.json()["query"]["pages"].values()))
        if "missing" in pagina:
            raise LookupError("el artículo no existe en Wikipedia")
        datos = {
            "extracto": pagina.get("extract", ""),
            "imagen": pagina.get("original", {}).get("source"),
            "url": pagina.get("fullurl"),
            "error": None,
        }
        cache.guardar(clave, datos)
        return datos
    except Exception as e:
        errores.append(_describir(e))

    return {"extracto": "", "imagen": None, "url": None, "error": " / ".join(errores)}


def _describir(e: Exception) -> str:
    if isinstance(e, requests.HTTPError) and e.response is not None:
        codigo = e.response.status_code
        if codigo == 403:
            return "Wikipedia bloqueó la solicitud (HTTP 403)"
        if codigo == 404:
            return "no se encontró el artículo (HTTP 404)"
        if codigo == 429:
            return "demasiadas solicitudes seguidas (HTTP 429)"
        return f"HTTP {codigo}"
    if isinstance(e, LookupError):
        return str(e)
    if isinstance(e, requests.Timeout):
        return "Wikipedia tardó demasiado en responder"
    if isinstance(e, requests.ConnectionError):
        return "no se pudo conectar con Wikipedia"
    return e.__class__.__name__
