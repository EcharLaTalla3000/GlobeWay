"""
Motor de cálculo de costos.

Separa siempre dos conceptos:
- COSTO DE VIDA EN DESTINO: lo que cuesta estar allí por día (comida,
  transporte local, actividades y alojamiento), sin contar el vuelo.
- COSTO TOTAL DEL VIAJE: vuelos ida y vuelta + estadía completa para todo el grupo.

Todos los cálculos internos se hacen en USD y se convierten al final.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from functools import lru_cache

from servicios.rutas import Red, Ruta
from servicios.vuelos import ORIGENES

RUTA_DATOS = Path(__file__).resolve().parent.parent / "datos" / "destinos.json"

TIPOS_ALOJAMIENTO = {
    "hostal": "Hostal (cama en dormitorio compartido)",
    "hotel": "Hotel 3★ (habitación doble)",
    "hotel_sup": "Hotel 4-5★ (habitación doble)",
    "depto": "Departamento completo",
}

# Estados según qué porcentaje del presupuesto consume el viaje.
# "ligeramente_sobre" cubre hasta un 15% por encima del presupuesto.
UMBRALES = [
    (0.60, "economico"),
    (0.85, "intermedio"),
    (1.00, "costoso"),
    (1.15, "ligeramente_sobre"),
    (math.inf, "fuera"),
]

ESTADOS = {
    "economico": {"etiqueta": "Económico (≤60% del presupuesto)", "color": "#34d399"},
    "intermedio": {"etiqueta": "Intermedio (60–85%)", "color": "#facc15"},
    "costoso": {"etiqueta": "Costoso (85–100%)", "color": "#fb923c"},
    "ligeramente_sobre": {"etiqueta": "Ligeramente sobre (hasta +15%)", "color": "#a78bfa"},
    "fuera": {"etiqueta": "Muy costoso / fuera de presupuesto", "color": "#ef4444"},
}

# Modo "Precios generales" (sin presupuesto): cuartiles del conjunto de destinos.
ESTADOS_GENERALES = [
    ("economico", "Económico", "#34d399"),
    ("intermedio", "Intermedio", "#facc15"),
    ("costoso", "Costoso", "#fb923c"),
    ("fuera", "Muy costoso", "#ef4444"),
]


def cargar_destinos() -> list[dict]:
    with open(RUTA_DATOS, encoding="utf-8") as f:
        return json.load(f)["destinos"]


@lru_cache(maxsize=1)
def red() -> Red:
    """Red de aeropuertos (se construye una sola vez)."""
    return Red(ORIGENES, cargar_destinos())


def unidades_alojamiento(tipo: str, viajeros: int) -> int:
    """Cuántas camas / habitaciones / departamentos hacen falta."""
    if tipo == "hostal":
        return viajeros                     # una cama por persona
    if tipo == "depto":
        return math.ceil(viajeros / 4)      # hasta 4 personas por departamento
    return math.ceil(viajeros / 2)          # habitaciones dobles


@dataclass
class Desglose:
    vuelo_pp: float           # ida y vuelta por persona
    vuelos: float             # vuelos de todo el grupo
    alojamiento: float        # estadía completa
    comida: float
    transporte: float
    actividades: float
    total: float
    diario_pp: float          # costo de vida por persona por día (sin vuelo)
    distancia_km: float
    ruta: Ruta


def calcular(destino: dict, origen: str, dias: int, viajeros: int, tipo_aloj: str) -> Desglose:
    noches = max(dias - 1, 1) if dias > 1 else 1
    ruta = red().ruta(origen, destino)
    vuelo_pp, km = ruta.precio_ida_vuelta_pp, ruta.km
    aloj_noche = destino[tipo_aloj] * unidades_alojamiento(tipo_aloj, viajeros)
    alojamiento = aloj_noche * noches
    comida = destino["comida"] * viajeros * dias
    transporte = destino["transporte"] * viajeros * dias
    actividades = destino["actividades"] * viajeros * dias
    vuelos = vuelo_pp * viajeros
    total = vuelos + alojamiento + comida + transporte + actividades
    diario_pp = (destino["comida"] + destino["transporte"] + destino["actividades"]
                 + aloj_noche / viajeros)
    return Desglose(vuelo_pp, vuelos, alojamiento, comida, transporte, actividades,
                    total, diario_pp, km, ruta)


def estado_presupuesto(total_usd: float, presupuesto_usd: float) -> str:
    if presupuesto_usd <= 0:
        return "fuera"
    ratio = total_usd / presupuesto_usd
    for limite, estado in UMBRALES:
        if ratio <= limite:
            return estado
    return "fuera"


def estados_cuartiles(valores: list[float]) -> tuple[list[str], list[float]]:
    """
    Clasifica cada valor en 4 grupos según los cuartiles del conjunto.
    Devuelve (estados, cortes) para poder mostrar los rangos en la leyenda.
    """
    if not valores:
        return [], []
    ordenados = sorted(valores)
    n = len(ordenados)
    cortes = [ordenados[min(int(n * q), n - 1)] for q in (0.25, 0.5, 0.75)]
    estados = [ESTADOS_GENERALES[sum(v > c for c in cortes)][0] for v in valores]
    return estados, cortes
