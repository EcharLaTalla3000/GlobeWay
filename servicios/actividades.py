"""
Actividades de un destino, desde Wikivoyage (guía de viajes libre, CC BY-SA).

Lee las secciones "Ver" y "Hacer" del artículo del destino en Wikivoyage en
español. Si trae pocas, suma lugares turísticos cercanos de Wikidata (museos,
parques, monumentos, playas, miradores…, con nombre y descripción en español,
ordenados por lo conocidos que son). Si aun así hay muy pocas, usa "See" y "Do"
de Wikivoyage en inglés. Las respuestas se guardan 7 días en caché.
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
MIN_ACTIVIDADES = 16      # bajo esto, se suman lugares de Wikidata
RADIO_KM = 12
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
    n_wikidata: int = 0     # cuántas vienen de Wikidata (para indicar la fuente)


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


def _de_wikivoyage(idioma: str, titulos: list[str]) -> tuple[list[Actividad], str, str | None]:
    """Actividades de la guía de Wikivoyage en `idioma`: (lista, url, error)."""
    error = None
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
            return actividades, f"https://{idioma}.wikivoyage.org/wiki/{quote(titulo_real.replace(' ', '_'))}", None
    return [], "", error


# Tipos de lugar de Wikidata que interesan a un viajero, y si son para "ver" o para "hacer"
TIPOS_WIKIDATA = {
    "Q570116": "ver",    # atracción turística
    "Q33506": "ver",     # museo
    "Q207694": "ver",    # museo de arte
    "Q4989906": "ver",   # monumento
    "Q23413": "ver",     # castillo
    "Q16560": "ver",     # palacio
    "Q57821": "ver",     # fortificación
    "Q16970": "ver",     # iglesia
    "Q2977": "ver",      # catedral
    "Q32815": "ver",     # mezquita
    "Q44539": "ver",     # templo
    "Q839954": "ver",    # sitio arqueológico
    "Q174782": "ver",    # plaza
    "Q12280": "ver",     # puente
    "Q15243209": "ver",  # barrio histórico
    "Q1440300": "ver",   # torre mirador
    "Q22698": "hacer",   # parque
    "Q1107656": "hacer", # jardín
    "Q46169": "hacer",   # parque nacional
    "Q40080": "hacer",   # playa
    "Q34038": "hacer",   # cascada
    "Q23397": "hacer",   # lago
    "Q6017969": "hacer", # mirador
    "Q43501": "hacer",   # zoológico
    "Q24354": "hacer",   # teatro
}
URL_WIKIDATA = "https://query.wikidata.org/sparql"


def _de_wikidata(lat: float, lon: float, excluir: set[str], parecidos: set[str]) -> list[Actividad]:
    """Lugares turísticos a menos de RADIO_KM del destino, los más conocidos primero."""
    valores = " ".join("wd:" + q for q in TIPOS_WIKIDATA)
    consulta = f"""SELECT ?item ?itemLabel ?d ?tipo ?tipoLabel ?sl ?art WHERE {{
  SERVICE wikibase:around {{ ?item wdt:P625 ?loc .
    bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "{RADIO_KM}" . }}
  ?item wdt:P31 ?tipo . VALUES ?tipo {{ {valores} }}
  ?item wikibase:sitelinks ?sl .
  OPTIONAL {{ ?item schema:description ?d FILTER(lang(?d) = "es") }}
  OPTIONAL {{ ?art schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
}} ORDER BY DESC(?sl) LIMIT 80"""
    r = requests.get(URL_WIKIDATA, headers={**_cabeceras(), "Accept": "application/sparql-results+json"},
                     params={"query": consulta, "format": "json"}, timeout=15)
    r.raise_for_status()
    salida, vistos = [], set()
    for b in r.json().get("results", {}).get("bindings", []):
        item = b["item"]["value"]
        nombre = (b.get("itemLabel") or {}).get("value", "").strip()
        clave = _normalizar(nombre)
        if item in vistos or not nombre or re.fullmatch(r"Q\d+", nombre) or clave in excluir:
            continue
        # Casi el mismo nombre que uno que ya está ("Mezquita Nacional" / "Mezquita Nacional de Abuya")
        if any(len(x) >= 8 and (x in clave or clave in x) for x in parecidos):
            continue
        vistos.add(item)
        excluir.add(clave)
        tipo_q = b["tipo"]["value"].rsplit("/", 1)[-1]
        desc = (b.get("d") or {}).get("value", "").strip()
        if not desc:
            desc = (b.get("tipoLabel") or {}).get("value", "").strip()
        salida.append(Actividad(nombre=nombre, tipo=TIPOS_WIKIDATA.get(tipo_q, "ver"),
                                descripcion=desc[:1].upper() + desc[1:] if desc else "",
                                web=(b.get("art") or {}).get("value", "")))
    return salida


def _normalizar(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def buscar(titulos: list[str], lat: float | None = None, lon: float | None = None) -> ResultadoActividades:
    """Actividades del destino. `titulos`: nombres posibles del artículo (en orden);
    `lat`/`lon`: ubicación, para sumar lugares cercanos de Wikidata si hay pocas."""
    titulos = [t for t in dict.fromkeys(t.strip() for t in titulos if t and t.strip())]
    clave = "act2:" + "|".join(titulos) + (f"|{lat:.2f},{lon:.2f}" if lat is not None and lon is not None else "")
    en_cache = cache.obtener(clave, TTL)
    if en_cache:
        d = en_cache[0]
        return ResultadoActividades([Actividad(**a) for a in d["actividades"]], d["idioma"], d["url"],
                                    n_wikidata=d.get("n_wikidata", 0))
    actividades, url, error = _de_wikivoyage("es", titulos)
    idioma = "es" if actividades else ""
    n_wd = 0
    if len(actividades) < MIN_ACTIVIDADES and lat is not None and lon is not None:
        nombres_wv = {_normalizar(a.nombre) for a in actividades}
        excluir = nombres_wv | {_normalizar(t) for t in titulos}
        try:
            extra = _de_wikidata(lat, lon, excluir, nombres_wv)[:MAX_ACTIVIDADES - len(actividades)]
            actividades += extra
            n_wd = len(extra)
        except (requests.RequestException, ValueError, KeyError) as e:
            error = error or f"no se pudo consultar Wikidata ({e.__class__.__name__})"
    if len(actividades) < 3:   # casi nada en español: la guía en inglés
        en, url_en, error_en = _de_wikivoyage("en", titulos)
        if en:
            actividades, url, idioma, n_wd = en, url_en, "en", 0
        error = error or error_en
    if not actividades:
        return ResultadoActividades([], "", "", error or "no hay actividades registradas para este destino")
    res = ResultadoActividades(actividades[:MAX_ACTIVIDADES], idioma, url, n_wikidata=n_wd)
    cache.guardar(clave, {"actividades": [a.__dict__ for a in res.actividades],
                          "idioma": idioma, "url": url, "n_wikidata": n_wd})
    return res


def enlace_tours(ciudad: str, pais: str) -> str:
    """Búsqueda de tours y entradas del destino en GetYourGuide."""
    return f"https://www.getyourguide.es/s/?q={quote_plus(ciudad + ' ' + pais)}"


def enlace_mapa(nombre: str, ciudad: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(nombre + ', ' + ciudad)}"
