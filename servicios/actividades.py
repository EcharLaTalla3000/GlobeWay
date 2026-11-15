"""
Actividades de un destino, desde Wikivoyage (guía de viajes libre, CC BY-SA).

Lee las secciones "Ver" y "Hacer" del artículo del destino en Wikivoyage en
español y, si no existe, las de "See" y "Do" en inglés. De cada lugar toma el
nombre, una descripción breve y, si existe, su sitio web y precio informado.
Las respuestas se guardan 7 días en caché.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import quote, quote_plus

import requests

from servicios import cache

TTL = 7 * 24 * 3600
MAX_ACTIVIDADES = 40
SECCIONES = {"es": {"ver": "Ver", "hacer": "Hacer"}, "en": {"ver": "See", "hacer": "Do"}}
PLANTILLAS = {"ver": "ver", "hacer": "hacer", "see": "ver", "do": "hacer", "listing": None,
              "marker": None, "veure": "ver", "fer": "hacer"}


@dataclass
class Actividad:
    nombre: str
    tipo: str               # "ver" (lugares para visitar) o "hacer" (actividades)
    descripcion: str
    web: str = ""
    precio: str = ""


@dataclass
class ResultadoActividades:
    actividades: list[Actividad] = field(default_factory=list)
    idioma: str = ""
    url: str = ""
    error: str | None = None


def _cabeceras() -> dict:
    contacto = os.getenv("WIKI_CONTACTO", "https://github.com/globe-travel-demo")
    return {"User-Agent": f"GlobeWay/0.1 ({contacto}) python-requests"}


def _texto_wiki(idioma: str, titulo: str) -> tuple[str, str] | None:
    r = requests.get(f"https://{idioma}.wikivoyage.org/w/api.php", headers=_cabeceras(), timeout=8,
                     params={"action": "parse", "page": titulo, "prop": "wikitext", "redirects": 1,
                             "format": "json", "formatversion": 2})
    r.raise_for_status()
    datos = r.json()
    if "error" in datos:
        return None
    p = datos.get("parse") or {}
    return p.get("title", titulo), p.get("wikitext") or ""


def _plantillas(texto: str):
    """Recorre las plantillas {{...}} de primer nivel (respeta llaves anidadas)."""
    i, n = 0, len(texto)
    while i < n:
        j = texto.find("{{", i)
        if j < 0:
            return
        nivel, k = 0, j
        while k < n:
            if texto.startswith("{{", k):
                nivel += 1
                k += 2
            elif texto.startswith("}}", k):
                nivel -= 1
                k += 2
                if nivel == 0:
                    break
            else:
                k += 1
        yield texto[j + 2:k - 2]
        i = k


def _limpiar(t: str) -> str:
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)                       # plantillas internas
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)    # [[enlace|texto]] -> texto
    t = re.sub(r"\[https?://\S+\s([^\]]*)\]", r"\1", t)        # [url texto] -> texto
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _campos(cuerpo: str) -> tuple[str, dict]:
    partes, nivel, actual = [], 0, ""
    for ch in cuerpo:   # separa por "|" que no estén dentro de [[ ]] o {{ }}
        if ch in "[{":
            nivel += 1
        elif ch in "]}":
            nivel -= 1
        if ch == "|" and nivel == 0:
            partes.append(actual)
            actual = ""
        else:
            actual += ch
    partes.append(actual)
    nombre = partes[0].strip().lower()
    campos = {}
    for p in partes[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            campos[k.strip().lower()] = v.strip()
    return nombre, campos


def _secciones(texto: str, idioma: str) -> dict[str, str]:
    """Texto de las secciones Ver/Hacer (o See/Do), con sus subsecciones."""
    buscadas = {v.lower(): k for k, v in SECCIONES[idioma].items()}
    salida, actual = {}, None
    for linea in texto.splitlines():
        m = re.match(r"^(=+)\s*(.*?)\s*=+\s*$", linea)
        if m:
            nivel, titulo = len(m.group(1)), m.group(2).lower()
            if nivel == 2:
                actual = buscadas.get(titulo)
            continue
        if actual:
            salida[actual] = salida.get(actual, "") + linea + "\n"
    return salida


def buscar(titulos: list[str]) -> ResultadoActividades:
    """Actividades del destino. `titulos`: nombres posibles del artículo (en orden)."""
    titulos = [t for t in dict.fromkeys(t.strip() for t in titulos if t and t.strip())]
    clave = "act:" + "|".join(titulos)
    en_cache = cache.obtener(clave, TTL)
    if en_cache:
        d = en_cache[0]
        return ResultadoActividades([Actividad(**a) for a in d["actividades"]], d["idioma"], d["url"])
    error = None
    for idioma in ("es", "en"):
        for titulo in titulos:
            try:
                encontrado = _texto_wiki(idioma, titulo)
            except (requests.RequestException, ValueError) as e:
                error = f"no se pudo consultar Wikivoyage ({e.__class__.__name__})"
                continue
            if not encontrado:
                continue
            titulo_real, texto = encontrado
            actividades = []
            for tipo_sec, cuerpo in _secciones(texto, idioma).items():
                for plantilla in _plantillas(cuerpo):
                    nombre_pl, campos = _campos(plantilla)
                    if nombre_pl not in PLANTILLAS:
                        continue
                    tipo = PLANTILLAS[nombre_pl] or tipo_sec
                    nombre = _limpiar(campos.get("nombre") or campos.get("name") or "")
                    if not nombre:
                        continue
                    desc = _limpiar(campos.get("descripción") or campos.get("descripcion")
                                    or campos.get("content") or "")
                    actividades.append(Actividad(
                        nombre=nombre, tipo=tipo,
                        descripcion=(desc[:280] + "…") if len(desc) > 280 else desc,
                        web=(campos.get("url") or "").strip(),
                        precio=_limpiar(campos.get("precio") or campos.get("price") or "")))
            if actividades:
                url = f"https://{idioma}.wikivoyage.org/wiki/{quote(titulo_real.replace(' ', '_'))}"
                res = ResultadoActividades(actividades[:MAX_ACTIVIDADES], idioma, url)
                cache.guardar(clave, {"actividades": [a.__dict__ for a in res.actividades],
                                      "idioma": idioma, "url": url})
                return res
    return ResultadoActividades([], "", "", error or "Wikivoyage no tiene actividades para este destino")


def enlace_tours(ciudad: str, pais: str) -> str:
    """Búsqueda de tours y entradas del destino en GetYourGuide."""
    return f"https://www.getyourguide.es/s/?q={quote_plus(ciudad + ' ' + pais)}"


def enlace_mapa(nombre: str, ciudad: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(nombre + ', ' + ciudad)}"
