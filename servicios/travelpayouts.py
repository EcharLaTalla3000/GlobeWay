"""
Precios REALES de vuelos desde Travelpayouts (datos de Aviasales).

Qué entrega:
- El pasaje ida y vuelta más barato que personas usuarias de Aviasales
  encontraron en sus búsquedas de las últimas ~48 horas, desde tu origen
  hacia cientos de destinos. Se combinan varias consultas (unas 5 a 8 por
  origen y fechas, guardadas 6 horas) para cubrir la mayor cantidad de destinos.
- Es un precio real pero "de búsquedas recientes": puede haber cambiado o
  agotarse. La app siempre lo muestra con esa etiqueta.
- Los destinos sin dato siguen usando la fórmula estimada (servicios/rutas.py).

Claves (en Settings → Secrets de Streamlit Cloud, Secretos de Colab o .env):
  TRAVELPAYOUTS_TOKEN   token de la API (obligatorio para precios reales)
  TRAVELPAYOUTS_MARKER  tu ID de socio, para que los enlaces a Aviasales sean de afiliado
  TRAVELPAYOUTS_MAX_DIARIO  (opcional) máximo de consultas por día, por defecto 500

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
URL_ULTIMOS = "https://api.travelpayouts.com/v2/prices/latest"
URL_AEROPUERTOS = "https://api.travelpayouts.com/data/en/airports.json"
URL_AVIASALES = "https://www.aviasales.com"

TTL_PRECIOS = 6 * 3600              # los precios se vuelven a pedir cada 6 horas
TTL_AEROPUERTOS = 30 * 24 * 3600    # la lista de aeropuertos cambia muy poco

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
    fechas_cercanas: bool = False   # True si no hubo precio para tus fechas exactas

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


def _pedir(url: str, params: dict, token: str) -> list[dict]:
    try:
        r = requests.get(url, params=params,
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
def _mes(d: date, n: int = 0) -> str:
    """'AAAA-MM' del mes de `d` más `n` meses."""
    m = d.month - 1 + n
    return f"{d.year + m // 12}-{m % 12 + 1:02d}"


def _consultas(llegada: date | None, salida: date | None) -> list[tuple[str, dict, int]]:
    """Lista de (fuente, parámetros, páginas) que se piden a Travelpayouts."""
    v3 = {"one_way": "false", "direct": "false", "sorting": "price", "currency": "usd", "limit": 1000}
    v2 = {"period_type": "year", "one_way": "false", "show_to_affiliates": "false",
          "sorting": "price", "currency": "usd", "limit": 1000}
    if llegada and salida:
        return [
            ("v3", {**v3, "departure_at": llegada.isoformat(), "return_at": salida.isoformat(),
                    "unique": "true"}, 1),
            ("v3", {**v3, "departure_at": _mes(llegada), "return_at": _mes(salida),
                    "unique": "false"}, 2),
            ("v2", v2, 2),
        ]
    base = date.today() + timedelta(days=30)
    return [
        ("v3", {**v3, "departure_at": _mes(base), "return_at": _mes(base), "unique": "false"}, 2),
        ("v3", {**v3, "departure_at": _mes(base), "return_at": _mes(base, 1), "unique": "false"}, 1),
        ("v3", {**v3, "departure_at": _mes(base, 1), "return_at": _mes(base, 1), "unique": "false"}, 2),
        ("v3", {**v3, "departure_at": _mes(base), "return_at": _mes(base, 1), "unique": "true"}, 1),
        ("v2", v2, 2),
    ]


def _normalizar(fuente: str, o: dict) -> dict | None:
    """Deja las ofertas de las dos fuentes (v3 y v2) con los mismos campos."""
    if fuente == "v2":
        if not o.get("value") or not o.get("return_date"):
            return None
        return {"destination": o.get("destination"), "destination_airport": None,
                "origin_airport": o.get("origin"), "price": o["value"], "airline": None,
                "departure_at": o.get("depart_date"), "return_at": o.get("return_date"),
                "transfers": o.get("number_of_changes"), "return_transfers": o.get("number_of_changes"),
                "link": ""}
    if not o.get("price") or not o.get("return_at"):
        return None
    campos = ("destination", "destination_airport", "origin_airport", "price", "airline",
              "departure_at", "return_at", "transfers", "return_transfers", "link")
    return {k: o.get(k) for k in campos}


def tolerancia(noches: int) -> int:
    """Diferencia de noches aceptada: ±3 en viajes cortos, ±la mitad en viajes largos."""
    return max(3, round(noches * 0.5))


def obtener_precios(origen: str, llegada: date | None, salida: date | None,
                    noches: int) -> TablaPrecios:
    """
    Pide a Travelpayouts los pasajes más baratos desde `origen` a todos los destinos,
    combinando varias consultas para cubrir la mayor cantidad posible de destinos:
    - Con fechas: exactamente esas fechas y, si no hay, fechas cercanas (±7 días al salir)
      con una duración parecida. Se prefieren siempre las fechas exactas.
    - Sin fechas: salidas en los próximos ~2 meses con duración parecida a la elegida.
    Nunca lanza errores: si algo falla, devuelve una tabla vacía con `error`.
    """
    tabla = TablaPrecios()
    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    if not token:
        tabla.error = "no hay TRAVELPAYOUTS_TOKEN configurado"
        return tabla

    tabla.ciudad_de = _ciudades()
    origen_tp = tabla.ciudad_de.get(origen, origen)   # SCL→SCL, JFK→NYC, EZE→BUE
    hoy = date.today()
    exactas = bool(llegada and salida)
    if exactas:
        tabla.periodo = (f"{_fecha_corta(llegada.isoformat())} – {_fecha_corta(salida.isoformat())}"
                         " o fechas cercanas")
        clave = f"tp2:{origen_tp}:{llegada}:{salida}"
    else:
        tabla.periodo = (f"viajes de duración parecida con salida entre {_mes_txt(hoy + timedelta(days=30))}"
                         f" y {_mes_txt(hoy + timedelta(days=75))}")
        clave = f"tp2:{origen_tp}:{_mes(hoy + timedelta(days=30))}"

    en_cache = cache.obtener(clave, TTL_PRECIOS)
    if en_cache:
        ofertas, tabla.consultado = en_cache
        tabla.desde_cache = True
    else:
        limite = int(os.getenv("TRAVELPAYOUTS_MAX_DIARIO", "500"))
        ofertas, errores = [], []
        for fuente, params, paginas in _consultas(llegada, salida):
            url = URL_PRECIOS if fuente == "v3" else URL_ULTIMOS
            try:
                for pagina in range(1, paginas + 1):
                    if not cache.registrar_llamada("travelpayouts", limite):
                        raise RuntimeError(f"se alcanzó el límite diario de {limite} consultas")
                    lote = _pedir(url, {**params, "origin": origen_tp, "page": pagina}, token)
                    ofertas += [n for o in lote if (n := _normalizar(fuente, o))]
                    if len(lote) < params["limit"]:
                        break
            except RuntimeError as e:
                errores.append(str(e))
                if "token" in str(e) or "límite" in str(e):
                    break
        if not ofertas:
            tabla.error = errores[0] if errores else "Travelpayouts no tiene precios recientes desde este origen"
            return tabla
        tabla.consultado = cache.guardar(clave, ofertas)   # solo se guarda si la consulta salió bien

    tol = tolerancia(noches)
    mejor_aero: dict[str, tuple] = {}
    mejor_ciudad: dict[str, tuple] = {}
    for o in ofertas:
        try:
            ida = date.fromisoformat((o.get("departure_at") or "")[:10])
            vuelta = date.fromisoformat((o.get("return_at") or "")[:10])
        except ValueError:
            continue
        n = (vuelta - ida).days
        if n < 1 or abs(n - noches) > tol:
            continue
        if exactas:
            if ida == llegada and vuelta == salida:
                nivel = 0
            elif abs((ida - llegada).days) <= 7:
                nivel = 1
            else:
                continue
        else:
            if not (hoy + timedelta(days=3) <= ida <= hoy + timedelta(days=120)):
                continue
            nivel = 0
        destino = o.get("destination")
        if not destino:
            continue
        p = PrecioReal(
            precio_pp=float(o["price"]), aerolinea=o.get("airline") or "",
            ida=ida.isoformat(), vuelta=vuelta.isoformat(),
            escalas_ida=int(o.get("transfers") or 0),
            escalas_vuelta=int(o.get("return_transfers") or 0),
            aeropuerto_origen=o.get("origin_airport") or origen_tp,
            aeropuerto_destino=o.get("destination_airport") or destino,
            ruta_link=o.get("link") or "", fechas_cercanas=bool(nivel),
        )
        # Se guarda la mejor oferta por aeropuerto y por ciudad (primero fechas exactas, luego precio)
        for dic, k in ((mejor_aero, o.get("destination_airport")), (mejor_ciudad, destino)):
            if k and (k not in dic or (nivel, p.precio_pp) < dic[k][0]):
                dic[k] = ((nivel, p.precio_pp), p)
    tabla.por_aeropuerto = {k: v[1] for k, v in mejor_aero.items()}
    tabla.por_ciudad = {k: v[1] for k, v in mejor_ciudad.items()}
    return tabla
