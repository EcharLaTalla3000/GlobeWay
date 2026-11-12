"""
Precios REALES de vuelos desde Travelpayouts (datos de Aviasales).

Qué entrega:
- El pasaje ida y vuelta más barato que personas usuarias de Aviasales
  encontraron en sus búsquedas de las últimas ~48 horas, desde tu origen
  hacia cientos de destinos, con UNA sola consulta por origen y fechas.
- Es un precio real pero "de búsquedas recientes": puede haber cambiado o
  agotarse. La app siempre lo muestra con esa etiqueta.
- Los destinos sin dato siguen usando la fórmula estimada (servicios/rutas.py).

Claves (en Settings → Secrets de Streamlit Cloud, Secretos de Colab o .env):
  TRAVELPAYOUTS_TOKEN   token de la API (obligatorio para precios reales)
  TRAVELPAYOUTS_MARKER  tu ID de socio, para que los enlaces a Aviasales sean de afiliado
  TRAVELPAYOUTS_MAX_DIARIO  (opcional) máximo de consultas por día, por defecto 300

Documentación: https://support.travelpayouts.com/hc/en-us/articles/203956163
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import requests

from servicios import cache

URL_PRECIOS = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
URL_AEROPUERTOS = "https://api.travelpayouts.com/data/en/airports.json"
URL_AVIASALES = "https://www.aviasales.com"

TTL_PRECIOS = 6 * 3600              # los precios se vuelven a pedir cada 6 horas
TTL_AEROPUERTOS = 30 * 24 * 3600    # la lista de aeropuertos cambia muy poco
PAGINAS_SIN_FECHAS = 3              # hasta 3.000 ofertas cuando no hay fechas fijas
TOLERANCIA_NOCHES = 3               # sin fechas: se aceptan viajes de ±3 noches

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def configurado() -> bool:
    return bool(os.getenv("TRAVELPAYOUTS_TOKEN"))


def marker() -> str:
    return (os.getenv("TRAVELPAYOUTS_MARKER") or "").strip()


# --------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------
@dataclass
class PrecioReal:
    precio_pp: float          # USD, ida y vuelta, por persona
    aerolinea: str            # código IATA de la aerolínea (ej. "LA")
    ida: str                  # fecha de ida "AAAA-MM-DD"
    vuelta: str               # fecha de vuelta "AAAA-MM-DD"
    escalas_ida: int
    escalas_vuelta: int
    aeropuerto_origen: str
    aeropuerto_destino: str
    ruta_link: str            # enlace relativo que entrega Aviasales

    def enlace(self, viajeros: int = 1) -> str:
        """Enlace a la búsqueda en Aviasales (con tu marker de afiliado si existe)."""
        if self.ruta_link:
            return armar_enlace(self.ruta_link, viajeros)
        try:
            return enlace_busqueda(self.aeropuerto_origen, self.aeropuerto_destino,
                                   date.fromisoformat(self.ida), date.fromisoformat(self.vuelta), viajeros)
        except ValueError:
            return armar_enlace("/", viajeros)

    def fechas_txt(self) -> str:
        return f"{_fecha_corta(self.ida)} – {_fecha_corta(self.vuelta)}"

    def escalas_txt(self) -> str:
        def uno(n: int) -> str:
            return "directo" if n == 0 else f"{n} escala{'s' if n > 1 else ''}"
        if self.escalas_ida == self.escalas_vuelta:
            return "directo" if self.escalas_ida == 0 else uno(self.escalas_ida) + " por trayecto"
        return f"ida {uno(self.escalas_ida)}, vuelta {uno(self.escalas_vuelta)}"


@dataclass
class TablaPrecios:
    por_aeropuerto: dict[str, PrecioReal] = field(default_factory=dict)
    por_ciudad: dict[str, PrecioReal] = field(default_factory=dict)
    ciudad_de: dict[str, str] = field(default_factory=dict)   # aeropuerto -> código de ciudad
    consultado: datetime | None = None
    desde_cache: bool = False
    error: str | None = None
    periodo: str = ""

    @property
    def cantidad(self) -> int:
        return len(self.por_ciudad)

    def buscar(self, codigos: list[str | None]) -> PrecioReal | None:
        """Busca primero por aeropuerto exacto y luego por ciudad (ej. CDG/ORY → PAR)."""
        codigos = [c for c in codigos if c and not c.startswith("@")]
        for c in codigos:
            if c in self.por_aeropuerto:
                return self.por_aeropuerto[c]
        for c in codigos:
            ciudad = self.ciudad_de.get(c, c)
            if ciudad in self.por_ciudad:
                return self.por_ciudad[ciudad]
        return None


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _fecha_corta(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
        return f"{d.day} {MESES[d.month - 1][:3]} {d.year}"
    except ValueError:
        return iso


def _mes_txt(d: date) -> str:
    return f"{MESES[d.month - 1]} {d.year}"


def armar_enlace(ruta_link: str, viajeros: int = 1) -> str:
    """Convierte el enlace relativo de Aviasales en uno completo, con pasajeros y marker."""
    link = ruta_link if ruta_link.startswith("/") else "/" + ruta_link
    link = re.sub(r"[\s\"'<>`]", "", link)   # por seguridad: el enlace va dentro de HTML
    # El número final de "/search/SCL1412MAD21121" es la cantidad de adultos
    if 1 <= viajeros <= 9:
        link = re.sub(r"^(/search/[A-Z]{3}\d{4}[A-Z]{3}(?:\d{4})?)\d", rf"\g<1>{viajeros}", link)
    m = marker()
    if m:
        link += ("&" if "?" in link else "?") + f"marker={m}"
    return URL_AVIASALES + link


def enlace_busqueda(origen: str, destino: str, ida: date, vuelta: date, viajeros: int) -> str:
    """Enlace a una búsqueda nueva en Aviasales (cuando no hay precio guardado)."""
    ruta = f"/search/{origen}{ida:%d%m}{destino}{vuelta:%d%m}{min(max(viajeros, 1), 9)}"
    return armar_enlace(ruta, viajeros)


def _ciudades() -> dict[str, str]:
    """Aeropuerto → código de ciudad (ej. CDG → PAR). Se guarda 30 días en caché."""
    en_cache = cache.obtener("tp:aeropuertos", TTL_AEROPUERTOS)
    if en_cache:
        return en_cache[0]
    try:
        r = requests.get(URL_AEROPUERTOS, timeout=30)
        r.raise_for_status()
        mapa = {a["code"]: a["city_code"] for a in r.json()
                if a.get("code") and a.get("city_code")}
    except Exception:
        return {}   # sin la lista igual funciona, solo con coincidencia exacta de aeropuerto
    if mapa:
        cache.guardar("tp:aeropuertos", mapa)
    return mapa


def _periodo(llegada: date | None, salida: date | None) -> tuple[str, str, bool, str]:
    """Devuelve (departure_at, return_at, fechas_exactas, texto para mostrar)."""
    if llegada and salida:
        return (llegada.isoformat(), salida.isoformat(), True,
                f"{_fecha_corta(llegada.isoformat())} – {_fecha_corta(salida.isoformat())}")
    base = date.today() + timedelta(days=30)
    return (base.strftime("%Y-%m"), base.strftime("%Y-%m"), False,
            f"viajes de duración similar en {_mes_txt(base)}")


def _noches(oferta: dict) -> int | None:
    try:
        ida = date.fromisoformat(oferta["departure_at"][:10])
        vuelta = date.fromisoformat(oferta["return_at"][:10])
        return (vuelta - ida).days
    except (KeyError, TypeError, ValueError):
        return None


def _pedir(params: dict, token: str) -> list[dict]:
    try:
        r = requests.get(URL_PRECIOS, params=params,
                         headers={"X-Access-Token": token, "Accept-Encoding": "gzip"},
                         timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"Travelpayouts no respondió ({e.__class__.__name__})") from e
    if r.status_code == 401:
        raise RuntimeError("el token de Travelpayouts no es válido (revisa TRAVELPAYOUTS_TOKEN)")
    if r.status_code == 429:
        raise RuntimeError("Travelpayouts pidió esperar: demasiadas consultas seguidas")
    if r.status_code >= 400:
        raise RuntimeError(f"Travelpayouts devolvió error {r.status_code}")
    cuerpo = r.json()
    if not cuerpo.get("success", True):
        raise RuntimeError(f"Travelpayouts: {cuerpo.get('error') or 'respuesta sin datos'}")
    datos = cuerpo.get("data") or []
    return datos if isinstance(datos, list) else []


# --------------------------------------------------------------------------
# Consulta principal
# --------------------------------------------------------------------------
def obtener_precios(origen: str, llegada: date | None, salida: date | None,
                    noches: int) -> TablaPrecios:
    """
    Pide a Travelpayouts los pasajes más baratos desde `origen` a todos los destinos.
    Con fechas: exactamente esas fechas. Sin fechas: el mes que viene, aceptando
    solo viajes de duración parecida (±3 noches) para no comparar peras con manzanas.
    Nunca lanza errores: si algo falla, devuelve una tabla vacía con `error`.
    """
    tabla = TablaPrecios()
    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    if not token:
        tabla.error = "no hay TRAVELPAYOUTS_TOKEN configurado"
        return tabla

    tabla.ciudad_de = _ciudades()
    ida, vuelta, exactas, tabla.periodo = _periodo(llegada, salida)
    origen_tp = tabla.ciudad_de.get(origen, origen)   # SCL→SCL, JFK→NYC, EZE→BUE
    clave = f"tp:precios:{origen_tp}:{ida}:{vuelta}"

    en_cache = cache.obtener(clave, TTL_PRECIOS)
    if en_cache:
        ofertas, tabla.consultado = en_cache
        tabla.desde_cache = True
    else:
        limite = int(os.getenv("TRAVELPAYOUTS_MAX_DIARIO", "300"))
        base = {"origin": origen_tp, "departure_at": ida, "return_at": vuelta,
                "one_way": "false", "direct": "false", "sorting": "price",
                "currency": "usd", "limit": 1000}
        ofertas = []
        try:
            paginas = 1 if exactas else PAGINAS_SIN_FECHAS
            for pagina in range(1, paginas + 1):
                if not cache.registrar_llamada("travelpayouts", limite):
                    if not ofertas:
                        raise RuntimeError(f"se alcanzó el límite diario de {limite} consultas")
                    break
                lote = _pedir({**base, "page": pagina,
                               "unique": "true" if exactas else "false"}, token)
                ofertas += lote
                if len(lote) < 1000:
                    break
        except RuntimeError as e:
            if not ofertas:
                tabla.error = str(e)
                return tabla
        # Se guarda solo lo necesario (y solo si la consulta salió bien)
        campos = ("destination", "destination_airport", "origin_airport", "price", "airline",
                  "departure_at", "return_at", "transfers", "return_transfers", "link")
        ofertas = [{k: o.get(k) for k in campos} for o in ofertas]
        tabla.consultado = cache.guardar(clave, ofertas)

    for o in ofertas:
        if not o.get("price") or not o.get("return_at") or not o.get("destination"):
            continue
        if not exactas:
            n = _noches(o)
            if n is None or abs(n - noches) > TOLERANCIA_NOCHES:
                continue
        p = PrecioReal(
            precio_pp=float(o["price"]), aerolinea=o.get("airline") or "—",
            ida=(o.get("departure_at") or "")[:10], vuelta=(o.get("return_at") or "")[:10],
            escalas_ida=int(o.get("transfers") or 0),
            escalas_vuelta=int(o.get("return_transfers") or 0),
            aeropuerto_origen=o.get("origin_airport") or origen,
            aeropuerto_destino=o.get("destination_airport") or o["destination"],
            ruta_link=o.get("link") or "",
        )
        # Se guarda la oferta más barata por aeropuerto y por ciudad
        for dic, k in ((tabla.por_aeropuerto, p.aeropuerto_destino), (tabla.por_ciudad, o["destination"])):
            if k not in dic or p.precio_pp < dic[k].precio_pp:
                dic[k] = p
    return tabla
