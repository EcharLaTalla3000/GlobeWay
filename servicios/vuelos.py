"""
Precios de vuelos.

Dos niveles, siempre identificados en la interfaz:

1. ESTIMADO (siempre disponible): fórmula por distancia ortodrómica entre
   aeropuertos. Es una aproximación de demostración, NO una tarifa real.

2. VERIFICADO EN TIEMPO REAL (opcional): API de Duffel, si existe la variable
   de entorno DUFFEL_ACCESS_TOKEN. Se consulta solo cuando el usuario lo pide
   para un destino concreto y con fechas, se guarda en caché y se limita la
   cantidad de llamadas diarias (DUFFEL_MAX_DIARIO, por defecto 30).
   Nota: con un token de prueba (duffel_test_...) Duffel devuelve ofertas de
   una aerolínea ficticia de pruebas; la app lo advierte.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime

import requests

from servicios import cache

# Aeropuertos de origen disponibles. Agregar más es tan simple como sumar filas.
ORIGENES = {
    "SCL": {"nombre": "Santiago (SCL)", "lat": -33.39, "lon": -70.79},
    "PMC": {"nombre": "Puerto Montt (PMC)", "lat": -41.44, "lon": -73.09},
    "CCP": {"nombre": "Concepción (CCP)", "lat": -36.77, "lon": -73.06},
    "ANF": {"nombre": "Antofagasta (ANF)", "lat": -23.44, "lon": -70.45},
    "PUQ": {"nombre": "Punta Arenas (PUQ)", "lat": -53.00, "lon": -70.85},
    "EZE": {"nombre": "Buenos Aires (EZE)", "lat": -34.82, "lon": -58.54},
    "LIM": {"nombre": "Lima (LIM)", "lat": -12.02, "lon": -77.11},
    "GRU": {"nombre": "São Paulo (GRU)", "lat": -23.43, "lon": -46.47},
    "BOG": {"nombre": "Bogotá (BOG)", "lat": 4.70, "lon": -74.15},
    "MEX": {"nombre": "Ciudad de México (MEX)", "lat": 19.44, "lon": -99.07},
    "MIA": {"nombre": "Miami (MIA)", "lat": 25.79, "lon": -80.29},
    "JFK": {"nombre": "Nueva York (JFK)", "lat": 40.64, "lon": -73.78},
    "MAD": {"nombre": "Madrid (MAD)", "lat": 40.49, "lon": -3.57},
    "LHR": {"nombre": "Londres (LHR)", "lat": 51.47, "lon": -0.45},
}

DUFFEL_URL = "https://api.duffel.com/air/offer_requests"
TTL_DUFFEL = 6 * 3600


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia ortodrómica (fórmula del haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def estimar_ida_vuelta_usd(origen: str, lat: float, lon: float) -> tuple[float, float]:
    """
    Estimación DEMO del pasaje ida y vuelta por persona en clase económica.
    Devuelve (precio_usd, distancia_km).

    Modelo: cargo fijo + tarifa por km decreciente con la distancia.
    Calibrado a mano para dar órdenes de magnitud razonables; no es un precio real.
    """
    o = ORIGENES[origen]
    km = distancia_km(o["lat"], o["lon"], lat, lon)
    if km < 250:  # muy cerca: se asume viaje por tierra, sin vuelo
        return 0.0, km
    por_km = 0.16 if km < 2000 else 0.11 if km < 8000 else 0.085
    precio = 90 + km * por_km
    return round(max(precio, 120), 0), km


@dataclass
class OfertaVerificada:
    precio_total: float      # total para todos los pasajeros, en la moneda indicada
    moneda: str
    aerolinea: str
    consultado: datetime
    modo_prueba: bool
    desde_cache: bool


class ErrorVuelos(Exception):
    pass


def duffel_configurado() -> bool:
    return bool(os.getenv("DUFFEL_ACCESS_TOKEN"))


def verificar_duffel(
    origen: str, destino_iata: str, ida: date, vuelta: date, pasajeros: int
) -> OfertaVerificada | None:
    """
    Consulta Duffel y devuelve la oferta más barata, o None si no hay ofertas.
    Lanza ErrorVuelos con un mensaje claro ante cualquier problema.
    """
    token = os.getenv("DUFFEL_ACCESS_TOKEN")
    if not token:
        raise ErrorVuelos("No hay DUFFEL_ACCESS_TOKEN configurado.")

    clave = f"duffel:{origen}:{destino_iata}:{ida}:{vuelta}:{pasajeros}"
    en_cache = cache.obtener(clave, TTL_DUFFEL)
    if en_cache:
        d, fecha = en_cache
        if d is None:
            return None
        return OfertaVerificada(d["precio"], d["moneda"], d["aerolinea"], fecha,
                                token.startswith("duffel_test"), True)

    limite = int(os.getenv("DUFFEL_MAX_DIARIO", "30"))
    if not cache.registrar_llamada("duffel", limite):
        raise ErrorVuelos(f"Se alcanzó el límite diario de {limite} consultas a Duffel.")

    cuerpo = {
        "data": {
            "slices": [
                {"origin": origen, "destination": destino_iata, "departure_date": ida.isoformat()},
                {"origin": destino_iata, "destination": origen, "departure_date": vuelta.isoformat()},
            ],
            "passengers": [{"type": "adult"} for _ in range(pasajeros)],
            "cabin_class": "economy",
        }
    }
    try:
        r = requests.post(
            DUFFEL_URL,
            params={"return_offers": "true", "supplier_timeout": 20000},
            json=cuerpo,
            headers={
                "Authorization": f"Bearer {token}",
                "Duffel-Version": "v2",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=40,
        )
    except requests.RequestException as e:
        raise ErrorVuelos(f"Duffel no respondió: {e.__class__.__name__}") from e

    if r.status_code >= 400:
        try:
            msg = r.json()["errors"][0].get("message", r.text[:200])
        except Exception:
            msg = r.text[:200]
        raise ErrorVuelos(f"Duffel devolvió error {r.status_code}: {msg}")

    ofertas = r.json().get("data", {}).get("offers", [])
    if not ofertas:
        cache.guardar(clave, None)
        return None

    mejor = min(ofertas, key=lambda o: float(o["total_amount"]))
    d = {
        "precio": float(mejor["total_amount"]),
        "moneda": mejor["total_currency"],
        "aerolinea": mejor.get("owner", {}).get("name", "—"),
    }
    fecha = cache.guardar(clave, d)
    return OfertaVerificada(d["precio"], d["moneda"], d["aerolinea"], fecha,
                            token.startswith("duffel_test"), False)
