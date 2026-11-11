"""
Popularidad turística y ranking de destinos.

Dos fuentes, siempre identificadas en la interfaz:

1. RANKING BASE (sin conexión): el orden de las listas de datos/ranking/*.txt,
   compilado manualmente.

2. RANKING EN VIVO (con conexión): visitas de los últimos 30 días al artículo de
   cada destino en Wikipedia en español (API pública de Wikimedia, sin clave).
   Es un indicador real y actualizado del interés por cada lugar, no una cifra
   oficial de turistas. Se consulta por lotes de 50 artículos y se guarda en
   caché 3 días.

Mapa de calor ("Más turísticos"):
   peso de un destino = llegadas internacionales del país (aprox.)
                        × participación del destino dentro de su país
   La participación sale de las visitas en Wikipedia (en vivo) o, sin conexión,
   del ranking base.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import requests

from servicios import cache

import time

URL = "https://es.wikipedia.org/w/api.php"
REINTENTO_SEG = 600          # tras un fallo, no reintentar antes de 10 minutos
_ultimo_fallo: dict = {"t": 0.0, "error": None}
TTL = 3 * 24 * 3600
LOTE = 50
DIAS = 30

# Llegadas de turistas internacionales por país, en millones por año.
# Valores APROXIMADOS de referencia (2023–2024), compilados manualmente a partir
# de cifras públicas de ONU Turismo y organismos nacionales. Solo se usan para
# ponderar el mapa de calor entre países.
LLEGADAS = {
    "FRA": 100, "ESP": 85, "USA": 66, "ITA": 57, "TUR": 55, "MEX": 42, "GBR": 38, "DEU": 35,
    "CHN": 35, "GRC": 33, "AUT": 31, "PRT": 30, "THA": 28, "ARE": 28, "SAU": 27, "JPN": 25,
    "NLD": 20, "HRV": 20, "MYS": 20, "POL": 19, "CAN": 18, "HUN": 15, "EGY": 15, "MAR": 14,
    "CZE": 13, "VNM": 12, "IDN": 12, "KOR": 11, "CHE": 11, "DNK": 11, "ALB": 10, "IND": 9,
    "TUN": 9, "BGR": 9, "KAZ": 9, "BEL": 9, "RUS": 8, "ZAF": 8, "DOM": 8, "KGZ": 8, "ARG": 7.4,
    "IRL": 7, "SWE": 7, "ROU": 7, "AUS": 7, "UZB": 7, "GEO": 7, "BRA": 6.6, "TWN": 6.5,
    "JOR": 6.4, "NOR": 6, "IRN": 6, "PHL": 5.5, "KHM": 5.4, "CHL": 5, "IRQ": 5, "SVN": 4.5,
    "COL": 4.2, "CYP": 4, "QAT": 4, "OMN": 4, "URY": 3.8, "FIN": 3.5, "PRI": 3.5, "LAO": 3.4,
    "DZA": 3.3, "JAM": 3.3, "PER": 3, "SLV": 3, "NZL": 3, "ISR": 3, "AZE": 2.6, "CRI": 2.6,
    "MNE": 2.5, "GTM": 2.5, "CUB": 2.4, "ARM": 2.3, "ISL": 2.2, "KEN": 2.1, "SVK": 2, "LTU": 2,
    "EST": 2, "SRB": 2, "PAN": 2, "LKA": 2, "TZA": 1.8, "BHS": 1.8, "LVA": 1.5, "BIH": 1.5,
    "CYN": 1.5, "LBN": 1.5, "CIV": 1.5, "ZWE": 1.5, "BWA": 1.5, "SEN": 1.4, "RWA": 1.4,
    "ECU": 1.3, "PRY": 1.3, "MMR": 1.3, "UGA": 1.3, "TJK": 1.3, "MKD": 1.2, "LUX": 1.2,
    "ZMB": 1.2, "NPL": 1.1, "GHA": 1.1, "BOL": 1, "HND": 1, "PAK": 1, "SYR": 1, "KWT": 1,
    "ETH": 1, "CMR": 1, "MOZ": 1, "LSO": 1, "FJI": 0.9, "NAM": 0.9, "SWZ": 0.8, "NIC": 0.7,
    "MWI": 0.7, "MNG": 0.65, "KOS": 0.6, "BGD": 0.6, "TGO": 0.6, "VEN": 0.5, "BLZ": 0.5,
    "BLR": 0.5, "UKR": 0.5, "NGA": 0.5, "MDA": 0.4, "TTO": 0.4, "COD": 0.4, "HTI": 0.3,
    "GUY": 0.3, "SUR": 0.3, "GUF": 0.1, "PSX": 0.3, "GMB": 0.3, "BEN": 0.3, "MDG": 0.3, "BRN": 0.2,
    "GAB": 0.2, "AGO": 0.2, "MLI": 0.15, "BFA": 0.15, "NER": 0.15, "COG": 0.15, "GRL": 0.1,
    "VUT": 0.1, "NCL": 0.1, "PNG": 0.1, "BTN": 0.1, "BDI": 0.1, "ERI": 0.1, "DJI": 0.1,
    "SDN": 0.1, "LBY": 0.1, "GIN": 0.1, "TCD": 0.1, "MRT": 0.1, "TLS": 0.08, "FLK": 0.06,
    "SLE": 0.06, "YEM": 0.05, "SOM": 0.05, "GNB": 0.05, "LBR": 0.05, "GNQ": 0.05, "SAH": 0.05,
    "SLB": 0.03, "AFG": 0.02, "SOL": 0.02, "SDS": 0.02, "CAF": 0.02, "TKM": 0.01, "PRK": 0.01,
}


@dataclass
class Popularidad:
    visitas: dict[str, int | None]   # id de destino -> visitas en 30 días (None = sin dato)
    en_vivo: bool                    # True si hay datos reales de Wikipedia
    actualizado: datetime | None
    cobertura: float                 # fracción de destinos con dato en vivo
    error: str | None = None


def _cabeceras() -> dict:
    contacto = os.getenv("WIKI_CONTACTO", "https://github.com/globe-travel-demo")
    ua = f"GlobeWay/0.1 ({contacto}) python-requests"
    return {"User-Agent": ua, "Api-User-Agent": ua}


def _consultar_lote(titulos: list[str]) -> dict[str, int | None]:
    """Visitas en los últimos DIAS días para hasta 50 títulos (resuelve redirecciones)."""
    params = {
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
        "prop": "pageviews", "pvipdays": DIAS, "titles": "|".join(titulos),
    }
    resultado: dict[str, int | None] = {}
    mapa = {t: t for t in titulos}            # título pedido -> título final
    while True:
        r = requests.get(URL, params=params, headers=_cabeceras(), timeout=20)
        r.raise_for_status()
        cuerpo = r.json()
        q = cuerpo.get("query", {})
        for n in q.get("normalized", []):
            for k, v in mapa.items():
                if v == n["from"]:
                    mapa[k] = n["to"]
        for red in q.get("redirects", []):
            for k, v in mapa.items():
                if v == red["from"]:
                    mapa[k] = red["to"]
        por_titulo = {}
        for p in q.get("pages", []):
            if p.get("missing"):
                por_titulo[p["title"]] = None
            else:
                vistas = p.get("pageviews") or {}
                por_titulo[p["title"]] = sum(v for v in vistas.values() if v)
        for pedido, final in mapa.items():
            if final in por_titulo:
                previo = resultado.get(pedido) or 0
                nuevo = por_titulo[final]
                resultado[pedido] = None if nuevo is None and not previo else (previo + (nuevo or 0))
        if "continue" not in cuerpo:
            break
        params.update(cuerpo["continue"])
    return resultado


def obtener_popularidad(destinos: list[dict]) -> Popularidad:
    """Visitas en Wikipedia para todos los destinos, con caché por artículo."""
    titulos = sorted({d["wiki"] for d in destinos})
    en_cache = cache.obtener_muchos([f"pv:{t}" for t in titulos], TTL)
    datos: dict[str, int | None] = {}
    fechas = []
    pendientes = []
    for t in titulos:
        c = en_cache.get(f"pv:{t}")
        if c is None:
            pendientes.append(t)
        else:
            datos[t] = c[0]
            fechas.append(c[1])

    error = None
    if pendientes and time.time() - _ultimo_fallo["t"] < REINTENTO_SEG:
        error = _ultimo_fallo["error"]
        pendientes = []
    if pendientes:
        lotes = [pendientes[i:i + LOTE] for i in range(0, len(pendientes), LOTE)]
        try:
            # Primer lote solo: si no hay conexión, se abandona rápido
            nuevos = _consultar_lote(lotes[0])
            if len(lotes) > 1:
                with ThreadPoolExecutor(max_workers=4) as ex:
                    for parcial in ex.map(_consultar_lote, lotes[1:]):
                        nuevos.update(parcial)
        except Exception as e:
            nuevos = locals().get("nuevos", {})
            error = (f"Wikipedia respondió HTTP {e.response.status_code}"
                     if isinstance(e, requests.HTTPError) and e.response is not None
                     else f"no se pudo consultar Wikipedia ({e.__class__.__name__})")
            _ultimo_fallo.update(t=time.time(), error=error)
        if nuevos:
            fechas.append(cache.guardar_muchos({f"pv:{t}": v for t, v in nuevos.items()}))
            datos.update(nuevos)
    fecha_min = min(fechas) if fechas else None

    visitas = {d["id"]: datos.get(d["wiki"]) for d in destinos}
    con_dato = sum(1 for v in visitas.values() if v)
    cobertura = con_dato / len(visitas) if visitas else 0
    return Popularidad(visitas, cobertura > 0.3, fecha_min, cobertura, error)


def calcular_ranking(destinos: list[dict], pop: Popularidad) -> dict[str, dict]:
    """
    Para cada destino devuelve {'rank': posición en su país, 'visitas', 'peso'}.
    Con datos en vivo, ordena por visitas (los que no tienen dato quedan al final
    en su orden base). Sin datos, usa el ranking base.
    """
    por_pais: dict[str, list[dict]] = {}
    for d in destinos:
        por_pais.setdefault(d["iso3"], []).append(d)

    salida = {}
    for iso, lista in por_pais.items():
        if pop.en_vivo:
            orden = sorted(lista, key=lambda d: (-(pop.visitas.get(d["id"]) or -1), d.get("rank_base", 99)))
        else:
            orden = sorted(lista, key=lambda d: d.get("rank_base", 99))

        # Participación de cada destino dentro del país
        if pop.en_vivo and any(pop.visitas.get(d["id"]) for d in lista):
            minimo = min(v for d in lista if (v := pop.visitas.get(d["id"]))) * 0.5
            bruto = {d["id"]: (pop.visitas.get(d["id"]) or minimo) for d in lista}
        else:
            bruto = {d["id"]: 1 / (d.get("rank_base", 10) ** 0.9) for d in lista}
        total = sum(bruto.values()) or 1
        llegadas = LLEGADAS.get(iso, 0.05)

        for pos, d in enumerate(orden, start=1):
            salida[d["id"]] = {
                "rank": pos,
                "visitas": pop.visitas.get(d["id"]),
                "peso": llegadas * bruto[d["id"]] / total,   # millones de llegadas atribuidas
            }
    return salida
