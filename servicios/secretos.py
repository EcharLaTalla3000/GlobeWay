"""
Lectura de claves (tokens de APIs) desde cualquier lugar donde estén guardadas.

Orden de búsqueda (la primera que tenga valor gana):
  1. Variables de entorno (por ejemplo, las que carga la celda de Colab desde 🔑 Secretos).
  2. Archivo .env en la carpeta del proyecto (uso local).
  3. "Secrets" de Streamlit Community Cloud (Settings → Secrets) o .streamlit/secrets.toml.

Las claves encontradas se dejan en os.environ, así el resto del código solo usa
os.getenv("NOMBRE") y no necesita saber de dónde vino cada una.
Nunca escribas tokens dentro del código ni los subas a GitHub.
"""
from __future__ import annotations

import os
from pathlib import Path

CLAVES = [
    "DUFFEL_ACCESS_TOKEN",
    "DUFFEL_MAX_DIARIO",
    "TRAVELPAYOUTS_TOKEN",
    "TRAVELPAYOUTS_MARKER",
    "BOOKING_API_KEY",
    "BOOKING_AFFILIATE_ID",
    "WIKI_CONTACTO",
]


def cargar() -> list[str]:
    """Carga las claves disponibles en os.environ y devuelve los nombres encontrados."""
    # 2) .env local (no pisa variables que ya existan)
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    except Exception:
        pass

    # 3) Secrets de Streamlit Cloud / .streamlit/secrets.toml
    try:
        import streamlit as st
        for nombre in CLAVES:
            if os.getenv(nombre):
                continue
            try:
                valor = st.secrets.get(nombre)
            except Exception:
                valor = None   # no hay archivo de secretos: es normal en Colab o local
                break
            if valor:
                os.environ[nombre] = str(valor)
    except Exception:
        pass

    return [n for n in CLAVES if os.getenv(n)]
