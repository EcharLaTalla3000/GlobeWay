"""
Alojamientos.

Arquitectura de proveedores: cada proveedor implementa `buscar(...)` y devuelve
una lista de `Alojamiento`. La app usa el primero que esté configurado.

- ProveedorDemo: genera opciones de EJEMPLO a partir de los costos promedio del
  destino. Son ficticias y la interfaz lo dice en cada tarjeta. El enlace lleva
  a una búsqueda real en Booking.com con los mismos parámetros, para que el
  usuario pueda consultar precios verdaderos.

- ProveedorBooking: punto de conexión preparado para la Demand API de
  Booking.com. Esa API exige ser socio afiliado aprobado; cuando existan
  credenciales, se implementa aquí. No se simulan sus respuestas.
"""
from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from servicios.costos import unidades_alojamiento


@dataclass
class Alojamiento:
    nombre: str
    tipo: str
    precio_noche_usd: float
    precio_total_usd: float
    zona: str
    calificacion: float | None
    disponible: bool | None      # None = desconocido (demo)
    enlace: str
    es_demo: bool
    foto: str | None = None


def enlace_busqueda_booking(ciudad: str, pais: str, llegada: date | None,
                            salida: date | None, huespedes: int) -> str:
    """URL de búsqueda pública en Booking.com (no usa la API)."""
    p = {"ss": f"{ciudad}, {pais}", "group_adults": huespedes, "no_rooms": 1}
    if llegada and salida:
        p["checkin"] = llegada.isoformat()
        p["checkout"] = salida.isoformat()
    return "https://www.booking.com/searchresults.html?" + urlencode(p)


# Prefijos y zonas genéricas para nombres de demostración
_NOMBRES = {
    "hostal": ["Hostal Ruta", "Mochila Hostel", "Casa Viajera", "Nómada Hostel"],
    "hotel": ["Hotel Plaza", "Hotel Mirador", "Hotel Central", "Hotel Jardín"],
    "hotel_sup": ["Gran Hotel", "Hotel Boutique Alto", "Palacio Suites", "Hotel Horizonte"],
    "depto": ["Depto. luminoso", "Loft céntrico", "Apartamento con vista", "Estudio moderno"],
}
_ZONAS = ["Centro", "Casco histórico", "Barrio bohemio", "Zona costera / ribera", "Cerca del transporte"]


class ProveedorDemo:
    nombre = "Demostración"

    def buscar(self, destino: dict, noches: int, huespedes: int, tipo: str | None,
               llegada: date | None, salida: date | None) -> list[Alojamiento]:
        # Semilla determinista para que las opciones no cambien en cada recarga
        semilla = int(hashlib.md5(destino["id"].encode()).hexdigest()[:8], 16)
        rnd = random.Random(semilla)
        tipos = [tipo] if tipo else ["hostal", "hotel", "hotel_sup", "depto"]
        enlace = enlace_busqueda_booking(destino["ciudad"].split(" (")[0].split(" /")[0],
                                         destino["pais"], llegada, salida, huespedes)
        salida_lista = []
        for t in tipos:
            for nombre in rnd.sample(_NOMBRES[t], 3 if tipo else 2):
                factor = rnd.uniform(0.75, 1.35)
                por_unidad = destino[t] * factor
                por_noche = por_unidad * unidades_alojamiento(t, huespedes)
                salida_lista.append(Alojamiento(
                    nombre=f"{nombre} (ejemplo)",
                    tipo=t,
                    precio_noche_usd=round(por_noche, 0),
                    precio_total_usd=round(por_noche * noches, 0),
                    zona=rnd.choice(_ZONAS),
                    calificacion=round(rnd.uniform(7.2, 9.5), 1),
                    disponible=None,
                    enlace=enlace,
                    es_demo=True,
                ))
        return sorted(salida_lista, key=lambda a: a.precio_total_usd)


class ProveedorBooking:
    nombre = "Booking.com Demand API"

    def __init__(self) -> None:
        self.clave = os.getenv("BOOKING_API_KEY")
        self.afiliado = os.getenv("BOOKING_AFFILIATE_ID")

    def configurado(self) -> bool:
        return bool(self.clave and self.afiliado)

    def buscar(self, *args, **kwargs) -> list[Alojamiento]:
        # Conectar aquí cuando Booking.com apruebe la cuenta de afiliado.
        # Seguir la documentación oficial de la Demand API y mapear cada
        # resultado a `Alojamiento(es_demo=False, disponible=True/False, ...)`.
        raise NotImplementedError(
            "La integración con Booking.com Demand API aún no está implementada. "
            "Requiere credenciales de afiliado aprobadas."
        )


def proveedor_activo():
    """Devuelve el proveedor real si está implementado y configurado; si no, el demo."""
    booking = ProveedorBooking()
    if booking.configurado():
        try:
            booking.buscar()
            return booking
        except NotImplementedError:
            pass
        except Exception:
            pass
    return ProveedorDemo()
