"""
Rutas aéreas con escalas (estimación).

Modelo:
- Una red de aeropuertos "hub" (grandes centros de conexión) con vuelos
  directos entre ellos si están a menos de 4.500 km, o si la ruta de larga
  distancia existe en la lista RUTAS_LARGAS.
- Cada aeropuerto secundario (destinos y orígenes que no son hub) se conecta
  con los hubs cercanos, con aeropuertos de su mismo país y con aeropuertos
  muy próximos.
- Se busca la combinación MÁS BARATA con un máximo de 4 escalas (5 tramos).
  Cada tramo suma un cargo fijo, así que una ruta con escalas cuesta más
  que una directa de la misma distancia, como en la realidad.

Es una aproximación de demostración: no consulta horarios ni aerolíneas reales.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

# código: (ciudad, lat, lon, país ISO3)
HUBS = {
    "SCL": ("Santiago", -33.39, -70.79, "CHL"),
    "EZE": ("Buenos Aires", -34.82, -58.54, "ARG"),
    "GRU": ("São Paulo", -23.43, -46.47, "BRA"),
    "LIM": ("Lima", -12.02, -77.11, "PER"),
    "BOG": ("Bogotá", 4.70, -74.15, "COL"),
    "PTY": ("Panamá", 9.07, -79.38, "PAN"),
    "MEX": ("Ciudad de México", 19.44, -99.07, "MEX"),
    "MIA": ("Miami", 25.79, -80.29, "USA"),
    "ATL": ("Atlanta", 33.64, -84.43, "USA"),
    "JFK": ("Nueva York", 40.64, -73.78, "USA"),
    "DFW": ("Dallas", 32.90, -97.04, "USA"),
    "LAX": ("Los Ángeles", 33.94, -118.41, "USA"),
    "YYZ": ("Toronto", 43.68, -79.63, "CAN"),
    "MAD": ("Madrid", 40.49, -3.57, "ESP"),
    "LIS": ("Lisboa", 38.77, -9.13, "PRT"),
    "LHR": ("Londres", 51.47, -0.45, "GBR"),
    "CDG": ("París", 49.01, 2.55, "FRA"),
    "AMS": ("Ámsterdam", 52.31, 4.76, "NLD"),
    "FRA": ("Fráncfort", 50.04, 8.56, "DEU"),
    "IST": ("Estambul", 41.26, 28.74, "TUR"),
    "DOH": ("Doha", 25.27, 51.61, "QAT"),
    "DXB": ("Dubái", 25.25, 55.36, "ARE"),
    "CAI": ("El Cairo", 30.12, 31.41, "EGY"),
    "CMN": ("Casablanca", 33.37, -7.59, "MAR"),
    "ADD": ("Adís Abeba", 8.98, 38.80, "ETH"),
    "NBO": ("Nairobi", -1.32, 36.93, "KEN"),
    "JNB": ("Johannesburgo", -26.14, 28.24, "ZAF"),
    "DEL": ("Delhi", 28.56, 77.10, "IND"),
    "BOM": ("Bombay", 19.09, 72.87, "IND"),
    "BKK": ("Bangkok", 13.69, 100.75, "THA"),
    "SIN": ("Singapur", 1.36, 103.99, "SGP"),
    "HKG": ("Hong Kong", 22.31, 113.91, "HKG"),
    "PVG": ("Shanghái", 31.14, 121.81, "CHN"),
    "NRT": ("Tokio", 35.77, 140.39, "JPN"),
    "ICN": ("Seúl", 37.46, 126.44, "KOR"),
    "SYD": ("Sídney", -33.94, 151.18, "AUS"),
    "AKL": ("Auckland", -37.01, 174.79, "NZL"),
}

# Rutas directas de larga distancia (> 4.500 km) entre hubs. Lista aproximada.
RUTAS_LARGAS = """
SCL-MAD SCL-LHR SCL-CDG SCL-MIA SCL-ATL SCL-JFK SCL-DFW SCL-LAX SCL-YYZ SCL-MEX SCL-SYD SCL-AKL SCL-PTY SCL-BOG
EZE-MAD SCL-GRU EZE-CDG EZE-FRA EZE-AMS EZE-IST EZE-MIA EZE-ATL EZE-JFK EZE-DFW EZE-MEX EZE-PTY EZE-BOG EZE-LIM
GRU-MAD GRU-LIS GRU-LHR GRU-CDG GRU-AMS GRU-FRA GRU-IST GRU-DOH GRU-DXB GRU-ADD GRU-JNB GRU-CMN
GRU-MIA GRU-ATL GRU-JFK GRU-DFW GRU-YYZ GRU-MEX GRU-PTY GRU-BOG GRU-LIM
BOG-MAD BOG-LHR BOG-CDG BOG-AMS BOG-FRA BOG-IST BOG-JFK BOG-YYZ BOG-LAX BOG-ATL
LIM-MAD LIM-AMS LIM-JFK LIM-LAX LIM-ATL LIM-DFW LIM-YYZ LIM-MEX
PTY-MAD PTY-AMS PTY-LAX PTY-JFK PTY-YYZ
MEX-MAD MEX-LHR MEX-CDG MEX-AMS MEX-FRA MEX-IST MEX-NRT MEX-ICN MEX-DOH
MIA-MAD MIA-LHR MIA-CDG MIA-FRA MIA-LIS MIA-IST MIA-DOH MIA-DXB
ATL-MAD ATL-LHR ATL-CDG ATL-AMS ATL-FRA ATL-LIS ATL-IST ATL-DOH ATL-DXB ATL-JNB ATL-ICN ATL-NRT
JFK-MAD JFK-LIS JFK-LHR JFK-CDG JFK-AMS JFK-FRA JFK-IST JFK-DOH JFK-DXB JFK-CAI JFK-CMN JFK-ADD JFK-JNB JFK-DEL JFK-BOM JFK-NRT JFK-ICN JFK-HKG
DFW-MAD DFW-LHR DFW-CDG DFW-AMS DFW-FRA DFW-DOH DFW-DXB DFW-NRT DFW-ICN DFW-SYD DFW-LAX
LAX-LHR LAX-CDG LAX-AMS LAX-FRA LAX-IST LAX-DOH LAX-DXB LAX-NRT LAX-ICN LAX-HKG LAX-PVG LAX-SIN LAX-SYD LAX-AKL LAX-JFK
YYZ-LHR YYZ-CDG YYZ-AMS YYZ-FRA YYZ-MAD YYZ-LIS YYZ-IST YYZ-DOH YYZ-DXB YYZ-DEL YYZ-NRT YYZ-ICN YYZ-HKG YYZ-LAX
LHR-JNB LHR-NBO LHR-ADD LHR-DEL LHR-BOM LHR-BKK LHR-SIN LHR-HKG LHR-PVG LHR-NRT LHR-ICN LHR-DXB LHR-DOH
CDG-JNB CDG-NBO CDG-ADD CDG-DEL CDG-BOM CDG-BKK CDG-SIN CDG-HKG CDG-PVG CDG-NRT CDG-ICN CDG-DXB CDG-DOH
AMS-JNB AMS-NBO AMS-DEL AMS-BKK AMS-SIN AMS-HKG AMS-PVG AMS-NRT AMS-ICN AMS-DXB AMS-DOH
FRA-JNB FRA-NBO FRA-ADD FRA-DEL FRA-BOM FRA-BKK FRA-SIN FRA-HKG FRA-PVG FRA-NRT FRA-ICN FRA-DXB FRA-DOH
MAD-JNB MAD-DOH MAD-DXB MAD-DEL MAD-NRT MAD-PVG MAD-ICN
IST-JNB IST-NBO IST-DEL IST-BOM IST-BKK IST-SIN IST-HKG IST-PVG IST-NRT IST-ICN
DOH-JNB DOH-NBO DOH-BKK DOH-SIN DOH-HKG DOH-PVG DOH-NRT DOH-ICN DOH-SYD DOH-AKL DOH-CMN
DXB-JNB DXB-NBO DXB-BKK DXB-SIN DXB-HKG DXB-PVG DXB-NRT DXB-ICN DXB-SYD DXB-AKL DXB-CMN
ADD-JNB ADD-DEL ADD-BKK ADD-HKG ADD-PVG ADD-NRT ADD-ICN ADD-CMN ADD-LHR
NBO-JNB NBO-BKK NBO-DEL
JNB-SYD JNB-SIN JNB-HKG
DEL-SIN DEL-HKG DEL-NRT DEL-SYD
BOM-SIN BOM-HKG
BKK-SYD BKK-NRT BKK-ICN BKK-PVG
SIN-SYD SIN-AKL SIN-NRT SIN-ICN SIN-PVG
HKG-SYD HKG-AKL
PVG-SYD PVG-AKL
NRT-SYD NRT-AKL
ICN-SYD ICN-AKL
"""

# Vuelos directos reales entre aeropuertos secundarios que las reglas no cubren
DIRECTOS_EXTRA = "PUQ-MPN CAY-CDG"  # CAY-CDG: Cayena–París (vuelos directos reales)

MAX_TRAMOS = 5  # = 4 escalas (incluye tramos domésticos desde aeropuertos regionales)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def precio_tramo(km: float) -> float:
    """Tarifa estimada de UN tramo (solo ida, por persona). Cargo fijo + tarifa por km decreciente."""
    if km < 1500:
        tarifa = 0.10
    elif km < 4000:
        tarifa = 0.075
    elif km < 8000:
        tarifa = 0.055
    else:
        tarifa = 0.045
    return 45 + km * tarifa


@dataclass
class Ruta:
    precio_ida_vuelta_pp: float
    km: float                       # distancia volada (suma de tramos, solo ida)
    codigos: list[str]              # ej. ["SCL", "MAD", "TUN"]
    coords: list[tuple[float, float]]
    por_tierra: bool = False
    etiquetas: list[str] | None = None   # nombres legibles de cada punto de la ruta
    traslado_km: float = 0.0             # tramo terrestre final (aeropuerto -> destino)

    def __post_init__(self):
        if self.etiquetas is None:
            self.etiquetas = list(self.codigos)

    @property
    def escalas(self) -> int:
        return max(len(self.codigos) - 2, 0)

    @property
    def aeropuerto_final(self) -> str | None:
        """Código IATA real del último aeropuerto (None si es un aeródromo estimado)."""
        c = self.codigos[-1]
        return None if c.startswith("@") else c

    def texto(self) -> str:
        if self.por_tierra:
            return "Por tierra (muy cerca del origen)"
        base = ("Vuelo directo" if self.escalas == 0 else
                f"{self.escalas} escala{'s' if self.escalas > 1 else ''} vía " + ", ".join(self.etiquetas[1:-1]))
        if self.traslado_km >= 30:
            base += f" + {round(self.traslado_km)} km por tierra"
        return base

    def recorrido(self) -> str:
        return "Por tierra" if self.por_tierra else " → ".join(self.etiquetas)


class Red:
    """Grafo de aeropuertos construido a partir de los hubs, los orígenes y los destinos."""

    def __init__(self, origenes: dict, destinos: list[dict]):
        # nodos: código -> (lat, lon, país)
        self.nodos: dict[str, tuple[float, float, str]] = {
            c: (v[1], v[2], v[3]) for c, v in HUBS.items()}
        for c, o in origenes.items():
            self.nodos.setdefault(c, (o["lat"], o["lon"], o.get("pais", "CHL")))
        # Nombre legible de cada nodo (para mostrar escalas)
        self.nombres: dict[str, str] = {c: c for c in self.nodos}

        # 1) Destinos con aeropuerto conocido: usan el hub de su ciudad si está
        #    a menos de 120 km (ej. Tokio-Haneda -> NRT); si no, su aeropuerto.
        self.nodo_de: dict[str, str] = {}
        sin_aeropuerto = []
        for d in destinos:
            if not d.get("iata"):
                sin_aeropuerto.append(d)
                continue
            cercano = min(HUBS, key=lambda h: distancia_km(d["lat"], d["lon"], HUBS[h][1], HUBS[h][2]))
            if distancia_km(d["lat"], d["lon"], HUBS[cercano][1], HUBS[cercano][2]) <= 120:
                self.nodo_de[d["id"]] = cercano
            else:
                self.nodo_de[d["id"]] = d["iata"]
                self.nodos.setdefault(d["iata"], (d["lat"], d["lon"], d["iso3"]))
                self.nombres.setdefault(d["iata"], d["iata"])

        # 2) Destinos sin aeropuerto: se llega al aeropuerto más cercano del mismo
        #    país (hasta 250 km) y luego por tierra. Si no hay ninguno, se asume
        #    un aeródromo regional estimado (código "@...").
        for d in sin_aeropuerto:
            # Aeropuerto del mismo país a menos de 250 km, o de cualquier país a menos de 120 km
            candidatos = [(distancia_km(d["lat"], d["lon"], v[0], v[1]), c)
                          for c, v in self.nodos.items() if not c.startswith("@")]
            candidatos = [(km, c) for km, c in candidatos
                          if (self.nodos[c][2] == d["iso3"] and km <= 250) or km <= 120]
            if candidatos:
                self.nodo_de[d["id"]] = min(candidatos)[1]
            else:
                codigo = "@" + d["id"]
                self.nodo_de[d["id"]] = codigo
                self.nodos[codigo] = (d["lat"], d["lon"], d["iso3"])
                self.nombres[codigo] = d["ciudad"].split(" (")[0]

        self.aristas: dict[str, dict[str, float]] = {c: {} for c in self.nodos}
        largas = {tuple(sorted(p.split("-"))) for p in RUTAS_LARGAS.split()}
        hubs = list(HUBS)
        otros = [c for c in self.nodos if c not in HUBS]

        def unir(a: str, b: str) -> None:
            km = self._km(a, b)
            self.aristas[a][b] = km
            self.aristas[b][a] = km

        # Hub–hub
        for i, a in enumerate(hubs):
            for b in hubs[i + 1:]:
                if self._km(a, b) <= 4500 or tuple(sorted((a, b))) in largas:
                    unir(a, b)

        # Aeródromos estimados ("@..."): solo vuelos domésticos. Se unen a los hubs
        # del país y, siempre, a los 2 aeropuertos reales más cercanos del país.
        estimados = [c for c in otros if c.startswith("@")]
        otros = [c for c in otros if not c.startswith("@")]
        for a in estimados:
            pais = self.nodos[a][2]
            for h in hubs:
                if self.nodos[h][2] == pais:
                    unir(a, h)
            reales = sorted((c for c in otros if self.nodos[c][2] == pais), key=lambda c: self._km(a, c))
            for c in reales[:2]:
                unir(a, c)
            for c in estimados:
                if c != a and self.nodos[c][2] == pais and self._km(a, c) <= 1500:
                    unir(a, c)

        # Secundario–hub
        for a in otros:
            pais = self.nodos[a][2]
            hubs_pais = [h for h in hubs if self.nodos[h][2] == pais]
            if hubs_pais:
                # País con hub propio: vuelos domésticos a sus hubs y solo a
                # hubs extranjeros muy cercanos (< 1.200 km)
                for h in hubs_pais:
                    unir(a, h)
                for h in hubs:
                    if h not in hubs_pais and self._km(a, h) <= 1200:
                        unir(a, h)
            else:
                # País sin hub: los 2 hubs más cercanos y todos los que estén a < 2.500 km
                por_cercania = sorted(hubs, key=lambda h: self._km(a, h))
                for i, h in enumerate(por_cercania):
                    if i < 2 or self._km(a, h) <= 2500:
                        unir(a, h)

        # Secundario–secundario: domésticos (< 3.500 km) o internacionales muy cortos (< 800 km
        # cuando ninguno de los dos países tiene hub propio, como en el Caribe o África)
        paises_con_hub = {v[3] for v in HUBS.values()}
        for i, a in enumerate(otros):
            for b in otros[i + 1:]:
                km = self._km(a, b)
                pa, pb = self.nodos[a][2], self.nodos[b][2]
                if (pa == pb and km <= 3500) or (
                        km <= 800 and pa not in paises_con_hub and pb not in paises_con_hub):
                    unir(a, b)

        for par in DIRECTOS_EXTRA.split():
            x, y = par.split("-")
            if x in self.nodos and y in self.nodos:
                unir(x, y)

    def _km(self, a: str, b: str) -> float:
        la, lo, _ = self.nodos[a]
        lb, lob, _ = self.nodos[b]
        return distancia_km(la, lo, lb, lob)

    @lru_cache(maxsize=64)
    def desde(self, origen: str) -> dict[str, tuple[float, list[str]]]:
        """
        Ruta más barata (solo ida) desde `origen` a todos los aeropuertos,
        con un máximo de MAX_TRAMOS tramos. Bellman-Ford limitado por tramos.
        Devuelve {código: (precio, [códigos de la ruta])}.
        """
        mejor = {origen: (0.0, [origen])}
        frontera = dict(mejor)
        for _ in range(MAX_TRAMOS):
            nueva = {}
            for nodo, (costo, camino) in frontera.items():
                for vecino, km in self.aristas[nodo].items():
                    if vecino in camino:
                        continue
                    c = costo + precio_tramo(km)
                    # Pequeña preferencia por menos escalas ante precios casi iguales
                    if vecino not in mejor or c < mejor[vecino][0] - 1:
                        mejor[vecino] = (c, camino + [vecino])
                        nueva[vecino] = mejor[vecino]
            frontera = nueva
            if not frontera:
                break
        return mejor

    def ruta(self, origen: str, destino: dict) -> Ruta:
        lo_, la_ = self.nodos[origen][1], self.nodos[origen][0]
        # Muy cerca del origen: se asume viaje por tierra
        if distancia_km(la_, lo_, destino["lat"], destino["lon"]) < 250:
            return Ruta(0.0, 0.0, [origen], [(la_, lo_)], por_tierra=True)
        tabla = self.desde(origen)
        codigo = self.nodo_de[destino["id"]]
        la, lo = self.nodos[codigo][0], self.nodos[codigo][1]
        traslado = distancia_km(la, lo, destino["lat"], destino["lon"])
        if codigo == origen:
            # El aeropuerto más cercano al destino es el mismo del origen: solo tierra
            return Ruta(0.0, 0.0, [origen], [(la, lo)], por_tierra=True)
        if codigo not in tabla:
            # Sin ruta dentro del máximo de escalas: se estima con un tramo extra
            # de conexión (cargo fijo adicional) para no subestimar el precio.
            km = self._km(origen, codigo)
            camino = [origen, codigo]
            precio = precio_tramo(km) * 1.35 + 90
        else:
            precio, camino = tabla[codigo]
            km = sum(self._km(a, b) for a, b in zip(camino, camino[1:]))
        return Ruta(round(2 * precio), km, camino, [self.nodos[c][:2] for c in camino],
                    etiquetas=[self.nombres.get(c, c) for c in camino], traslado_km=traslado)
