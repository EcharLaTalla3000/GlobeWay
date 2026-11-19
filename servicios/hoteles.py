"""
Hoteles con precios reales (LiteAPI / Nuitée).

Qué hace:
- Busca los hoteles que hay alrededor del destino (radio de 15 km).
- Los agrupa por estrellas (5★ a 1★) y toma hasta 10 por nivel.
- Pide el precio mínimo disponible de cada uno para tus fechas y viajeros.

Clave (en Settings → Secrets de Streamlit Cloud, Secretos de Colab o .env):
  LITEAPI_KEY            tu clave de LiteAPI (https://dashboard.liteapi.travel)
                         - "sand_..." = clave de PRUEBA: los precios NO son reales y la app lo avisa.
                         - "prod_..." = clave real.
  LITEAPI_WHITELABEL_URL (opcional) dirección de tu sitio de reservas de LiteAPI, para que
                         los enlaces "Reservar" vayan ahí (y ganes comisión). Si no está,
                         los enlaces llevan a la búsqueda del hotel en Booking.com.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date
from urllib.parse import quote_plus

import requests

from servicios import cache

URL = "https://api.liteapi.travel/v3.0"
TTL_HOTELES = 30 * 24 * 3600     # la lista de hoteles cambia poco
TTL_PRECIOS = 6 * 3600
# Tope de consultas a LiteAPI por día (protege de cobros si la clave es de producción).
# Se puede cambiar con el secreto LITEAPI_MAX_DIARIO.
MAX_DIARIO = 100


def _contar_consulta() -> None:
    limite = int(os.getenv("LITEAPI_MAX_DIARIO", str(MAX_DIARIO)))
    if not cache.registrar_llamada("liteapi", limite):
        raise RuntimeError(f"se alcanzó el límite diario de {limite} consultas de hoteles; "
                           "vuelve a intentarlo mañana")
POR_NIVEL = 10
CANDIDATOS_POR_NIVEL = 20        # se piden más, porque no todos tienen disponibilidad


def configurado() -> bool:
    return bool(os.getenv("LITEAPI_KEY"))


def es_prueba() -> bool:
    return (os.getenv("LITEAPI_KEY") or "").startswith(("sand", "test"))


@dataclass
class Hotel:
    id: str
    nombre: str
    estrellas: int
    nota: float | None          # calificación de huéspedes (0–10), si existe
    resenas: int | None
    direccion: str
    foto: str
    precio_total: float         # USD, toda la estadía, todas las habitaciones
    enlace: str


@dataclass
class ResultadoHoteles:
    por_estrellas: dict[int, list[Hotel]]
    prueba: bool
    error: str | None = None
    consultado: object = None

    @property
    def cantidad(self) -> int:
        return sum(len(v) for v in self.por_estrellas.values())


def _cabeceras() -> dict:
    return {"X-API-Key": os.getenv("LITEAPI_KEY", ""), "accept": "application/json",
            "content-type": "application/json"}


def _habitaciones(viajeros: int) -> list[dict]:
    """Habitaciones dobles; si el número es impar, una individual."""
    hab = [{"adults": 2} for _ in range(viajeros // 2)]
    if viajeros % 2:
        hab.append({"adults": 1})
    return hab or [{"adults": 1}]


def _enlace(h: dict, ciudad: str, ida: date, vuelta: date, viajeros: int) -> str:
    base = (os.getenv("LITEAPI_WHITELABEL_URL") or "").rstrip("/")
    if base:
        return (f"{base}/hotels/{h['id']}?checkin={ida.isoformat()}&checkout={vuelta.isoformat()}"
                f"&adults={viajeros}")
    return (f"https://www.booking.com/searchresults.es.html?ss={quote_plus(h.get('name', '') + ' ' + ciudad)}"
            f"&checkin={ida.isoformat()}&checkout={vuelta.isoformat()}&group_adults={viajeros}"
            f"&no_rooms={len(_habitaciones(viajeros))}")


def _hoteles_cerca(lat: float, lon: float) -> list[dict]:
    clave = f"lite:hoteles:{lat:.3f}:{lon:.3f}"
    en_cache = cache.obtener(clave, TTL_HOTELES)
    if en_cache:
        return en_cache[0]
    _contar_consulta()
    r = requests.get(f"{URL}/data/hotels", headers=_cabeceras(), timeout=25,
                     params={"latitude": lat, "longitude": lon, "radius": 15000, "limit": 1000})
    if r.status_code == 401:
        raise RuntimeError("la clave LITEAPI_KEY no es válida")
    r.raise_for_status()
    datos = r.json().get("data") or []
    campos = ("id", "name", "stars", "starRating", "rating", "reviewCount", "address",
              "main_photo", "thumbnail")
    hoteles = [{k: h.get(k) for k in campos} for h in datos if h.get("id")]
    if hoteles:
        cache.guardar(clave, hoteles)
    return hoteles


def _precios(ids: list[str], ida: date, vuelta: date, viajeros: int) -> dict[str, float]:
    huella = hashlib.md5(",".join(sorted(ids)).encode()).hexdigest()[:16]
    clave = f"lite:precios:{ida}:{vuelta}:{viajeros}:{huella}"
    en_cache = cache.obtener(clave, TTL_PRECIOS)
    if en_cache:
        return en_cache[0]
    cuerpo = {"hotelIds": ids, "occupancies": _habitaciones(viajeros),
              "checkin": ida.isoformat(), "checkout": vuelta.isoformat(),
              "currency": "USD", "guestNationality": "CL", "timeout": 10}
    _contar_consulta()
    r = requests.post(f"{URL}/hotels/min-rates", headers=_cabeceras(), json=cuerpo, timeout=30)
    if r.status_code == 401:
        raise RuntimeError("la clave LITEAPI_KEY no es válida")
    r.raise_for_status()
    salida = {}
    for x in r.json().get("data") or []:
        precio = x.get("price") or x.get("suggestedSellingPrice") or x.get("minRate")
        if isinstance(precio, dict):
            precio = precio.get("amount")
        if x.get("hotelId") and precio:
            salida[x["hotelId"]] = float(precio)
    cache.guardar(clave, salida)
    return salida


def buscar(lat: float, lon: float, ciudad: str, ida: date, vuelta: date,
           viajeros: int) -> ResultadoHoteles:
    """Hasta 10 hoteles por nivel de estrellas, con su precio real para la estadía.
    Nunca lanza errores: si algo falla, devuelve el resultado vacío con `error`."""
    if not configurado():
        return ResultadoHoteles({}, False, "no hay LITEAPI_KEY configurada")
    try:
        hoteles = _hoteles_cerca(lat, lon)
        if not hoteles:
            return ResultadoHoteles({}, es_prueba(), "LiteAPI no tiene hoteles registrados cerca de este destino")
        por_nivel: dict[int, list[dict]] = {}
        for h in hoteles:
            e = h.get("stars") or h.get("starRating") or 0
            try:
                e = int(round(float(e)))
            except (TypeError, ValueError):
                e = 0
            if 1 <= e <= 5:
                por_nivel.setdefault(e, []).append(h)
        # Dentro de cada nivel, primero los mejor evaluados (más reseñas y mejor nota)
        candidatos = []
        for e, lista in por_nivel.items():
            lista.sort(key=lambda h: (-(h.get("reviewCount") or 0), -(h.get("rating") or 0)))
            candidatos += lista[:CANDIDATOS_POR_NIVEL]
        if not candidatos:
            return ResultadoHoteles({}, es_prueba(), "los hoteles de la zona no tienen categoría de estrellas")
        precios = _precios([h["id"] for h in candidatos], ida, vuelta, viajeros)
    except (RuntimeError, requests.RequestException, ValueError) as e:
        return ResultadoHoteles({}, es_prueba(), str(e) if isinstance(e, RuntimeError)
                                else f"LiteAPI no respondió bien ({e.__class__.__name__})")

    resultado: dict[int, list[Hotel]] = {}
    for h in candidatos:
        if h["id"] not in precios:
            continue   # sin disponibilidad para esas fechas
        e = int(round(float(h.get("stars") or h.get("starRating") or 0)))
        nota = h.get("rating")
        resultado.setdefault(e, []).append(Hotel(
            id=h["id"], nombre=h.get("name") or "Hotel", estrellas=e,
            nota=float(nota) if nota else None, resenas=h.get("reviewCount"),
            direccion=h.get("address") or "", foto=h.get("thumbnail") or h.get("main_photo") or "",
            precio_total=precios[h["id"]], enlace=_enlace(h, ciudad, ida, vuelta, viajeros)))
    for e in resultado:
        resultado[e] = sorted(resultado[e], key=lambda x: x.precio_total)[:POR_NIVEL]
    return ResultadoHoteles(dict(sorted(resultado.items(), reverse=True)), es_prueba(),
                            None if resultado else "no hay disponibilidad para esas fechas")
