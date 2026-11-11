"""
Componente del globo 3D.

Usa Globe.gl (Three.js/WebGL) dentro de un iframe de Streamlit. Se eligió
Globe.gl sobre CesiumJS porque no requiere token, pesa poco, y trae de serie
polígonos de países, puntos, arcos y anillos, que es lo que este proyecto
necesita. CesiumJS conviene si más adelante se quiere terreno 3D real.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit.components.v1 as components

PLANTILLA = Path(__file__).with_name("globo.html").read_text(encoding="utf-8")


def mostrar_globo(datos: dict, alto: int = 640) -> None:
    """Renderiza el globo con los datos ya calculados (colores, totales, textos)."""
    html = PLANTILLA.replace("__DATOS__", json.dumps(datos, ensure_ascii=False))
    components.html(html, height=alto, scrolling=False)
