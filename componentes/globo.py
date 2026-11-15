"""
Componente del globo 3D (bidireccional).

Usa Globe.gl (Three.js/WebGL). La página está en componentes/globo_web/index.html
y se carga como "componente de Streamlit" sin React: los datos llegan por
mensajes y, cuando la persona toca un destino o un país, el globo le devuelve
a Python qué se tocó. Así la app puede actualizar las pestañas de abajo.

Valor que devuelve mostrar_globo() (o None si aún no se ha tocado nada):
    {"tipo": "destino", "id": "...", "iso3": "ITA", "t": 1731400000000}
    {"tipo": "pais", "iso3": "ITA", "nombre": "Italy", "t": ...}
    {"tipo": "cerrar", "t": ...}
"t" es la hora del clic: sirve para no procesar dos veces el mismo clic.
"""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_globo = components.declare_component(
    "globo_globeway", path=str(Path(__file__).with_name("globo_web")))


def mostrar_globo(datos: dict, alto: int = 640, enfoque: dict | None = None,
                  key: str = "globo") -> dict | None:
    """Dibuja el globo con los datos ya calculados y devuelve el último clic.
    `enfoque` = {"id": destino, "t": hora}: el globo vuela a ese destino y abre su ficha
    (lo usa el botón "Sorpréndeme")."""
    return _globo(datos=datos, alto=alto, enfoque=enfoque, key=key, default=None)
