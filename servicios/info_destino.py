"""
Información general y fotografía de cada destino desde Wikipedia en español
(API pública, sin clave). Se guarda en caché 7 días.

Wikimedia rechaza (HTTP 403) las solicitudes sin un User-Agent que identifique
la aplicación y un medio de contacto. Se puede definir WIKI_CONTACTO en .env
(una URL o correo tuyo) para cumplir su política.
"""
from __future__ import annotations

import os
import re
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
    clave = f"wiki2:{titulo}"   # "wiki2": ahora también guarda varias fotos
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
        datos["fotos"] = fotos(titulo, datos["imagen"])
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
        datos["fotos"] = fotos(pagina.get("title") or titulo, datos["imagen"])
        cache.guardar(clave, datos)
        return datos
    except Exception as e:
        errores.append(_describir(e))

    return {"extracto": "", "imagen": None, "url": None, "fotos": [], "error": " / ".join(errores)}


# --------------------------------------------------------------------------
# Galería de fotos del destino
# --------------------------------------------------------------------------
# Se toman las fotos del artículo de Wikipedia en el orden en que aparecen (las
# primeras suelen ser las más representativas) y se descartan mapas, banderas,
# escudos, logos, gráficos y fotos antiguas.
_EXCLUIR = re.compile(
    r"(^|[\s_(,.-])(map|mapa|plano|arms|seal|icon|coin|firma|sello|clima)([\s_(),.-]|$)|"
    r"flag|bandera|escudo|coat_of|emblem|logo|locator|location|localiza|situaci|chart|"
    r"grafic|gráfic|diagram|climate|nasa|commons-|wiki|signature|portrait|retrato|stamp|"
    r"poster|banknote|billete|blason|wappen", re.I)
_ANIO_ANTIGUO = re.compile(r"(?<!\d)(1[5-8]\d\d|19[0-5]\d)(?!\d)")
_CAMARA = re.compile(r"^(IMG|DSC|DSCN|DSCF|PICT|CIMG|SAM|GOPR|P\d{3})", re.I)


def _sirve(nombre: str) -> bool:
    """¿El nombre del archivo parece una foto actual del lugar?"""
    if not re.search(r"\.(jpe?g|webp)$", nombre, re.I) or _EXCLUIR.search(nombre):
        return False
    # Fotos antiguas ("Vista de Cuzco 1886"), salvo nombres de cámara tipo "IMG_1834"
    return not (_ANIO_ANTIGUO.search(nombre) and not _CAMARA.search(nombre))


MAX_FOTOS = 6


def fotos(titulo: str, principal: str | None = None) -> list[str]:
    """Hasta 6 fotos del artículo (URL de 960 px de ancho). La foto principal va primero.
    Nunca lanza errores: si algo falla devuelve solo la principal (o nada)."""
    lista = [_liviana(principal)] if principal else []
    try:
        r = requests.get(URL_ACTION, headers=_cabeceras(), timeout=10, params={
            "action": "parse", "format": "json", "page": titulo, "redirects": 1, "prop": "images"})
        r.raise_for_status()
        nombres = [n for n in (r.json().get("parse") or {}).get("images", []) if _sirve(n)][:20]
        if not nombres:
            return lista
        r = requests.get(URL_ACTION, headers=_cabeceras(), timeout=10, params={
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|size|mime",
            "iiurlwidth": 960, "titles": "|".join("Archivo:" + n for n in nombres)})
        r.raise_for_status()
        q = r.json().get("query") or {}
        normal = {x["from"]: x["to"] for x in q.get("normalized", [])}
        por_titulo = {p.get("title"): p for p in (q.get("pages") or {}).values()}
        base_principal = _nombre_archivo(principal)
        for n in nombres:   # se respeta el orden del artículo
            p = por_titulo.get(normal.get("Archivo:" + n, "Archivo:" + n)) or {}
            info = (p.get("imageinfo") or [{}])[0]
            if not info.get("thumburl"):
                continue
            if base_principal and _nombre_archivo(info.get("url")) == base_principal:
                lista[0] = info["thumburl"]   # la foto principal, en versión liviana (960 px)
                continue
            w, h = info.get("width") or 0, info.get("height") or 0
            if w < 640 or h < 400 or not (0.6 <= w / h <= 2.2):
                continue   # muy chica, muy alargada (panorámicas) o muy alta
            lista.append(info["thumburl"])
            if len(lista) >= MAX_FOTOS:
                break
    except Exception:
        pass
    return lista


def _liviana(url: str) -> str:
    """Si la foto principal es una miniatura enorme ("/thumb/.../3840px-..."), la pide a 960 px."""
    m = re.search(r"/(\d+)px-[^/]+$", url or "")
    if m and "/thumb/" in url and int(m.group(1)) > 960:
        return url[:m.start(1)] + "960" + url[m.end(1):]
    return url


def _nombre_archivo(url: str | None) -> str:
    """Nombre del archivo de una URL de Wikimedia (sirve para comparar miniatura y original)."""
    if not url:
        return ""
    partes = url.split("/")
    if "thumb" in partes and len(partes) >= 2:
        return partes[-2].lower()
    return partes[-1].lower()


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
