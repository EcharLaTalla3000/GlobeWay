"""
Caché persistente simple en SQLite.

Guarda respuestas de APIs externas con su fecha y hora, para:
- no repetir llamadas (control de costos),
- mostrar cuándo se actualizó cada dato,
- llevar un contador diario de solicitudes por proveedor (límite de uso).

En la Etapa 2 esto se reemplaza por PostgreSQL/Redis sin cambiar la interfaz.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, date
from pathlib import Path

RUTA_DB = Path(__file__).resolve().parent.parent / "datos" / "cache.db"


def _conexion() -> sqlite3.Connection:
    con = sqlite3.connect(RUTA_DB)
    con.execute(
        "CREATE TABLE IF NOT EXISTS respuestas ("
        " clave TEXT PRIMARY KEY, valor TEXT NOT NULL, fecha TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS uso_api ("
        " proveedor TEXT, dia TEXT, llamadas INTEGER, PRIMARY KEY (proveedor, dia))"
    )
    return con


def obtener(clave: str, max_segundos: int) -> tuple[object, datetime] | None:
    """Devuelve (valor, fecha) si existe y no ha vencido; si no, None."""
    with _conexion() as con:
        fila = con.execute(
            "SELECT valor, fecha FROM respuestas WHERE clave = ?", (clave,)
        ).fetchone()
    if not fila:
        return None
    fecha = datetime.fromisoformat(fila[1])
    if (datetime.now(timezone.utc) - fecha).total_seconds() > max_segundos:
        return None
    return json.loads(fila[0]), fecha


def obtener_muchos(claves: list[str], max_segundos: int) -> dict[str, tuple[object, datetime]]:
    """Lee varias claves vigentes en una sola consulta (para miles de entradas)."""
    salida = {}
    ahora = datetime.now(timezone.utc)
    with _conexion() as con:
        for i in range(0, len(claves), 500):
            parte = claves[i:i + 500]
            filas = con.execute(
                f"SELECT clave, valor, fecha FROM respuestas WHERE clave IN ({','.join('?' * len(parte))})",
                parte).fetchall()
            for clave, valor, fecha in filas:
                f = datetime.fromisoformat(fecha)
                if (ahora - f).total_seconds() <= max_segundos:
                    salida[clave] = (json.loads(valor), f)
    return salida


def guardar_muchos(pares: dict[str, object]) -> datetime:
    ahora = datetime.now(timezone.utc)
    with _conexion() as con:
        con.executemany(
            "INSERT OR REPLACE INTO respuestas (clave, valor, fecha) VALUES (?, ?, ?)",
            [(k, json.dumps(v), ahora.isoformat()) for k, v in pares.items()])
    return ahora


def guardar(clave: str, valor: object) -> datetime:
    """Guarda un valor serializable en JSON y devuelve la fecha registrada."""
    ahora = datetime.now(timezone.utc)
    with _conexion() as con:
        con.execute(
            "INSERT OR REPLACE INTO respuestas (clave, valor, fecha) VALUES (?, ?, ?)",
            (clave, json.dumps(valor), ahora.isoformat()),
        )
    return ahora


def registrar_llamada(proveedor: str, limite_diario: int) -> bool:
    """
    Suma una llamada al contador del día. Devuelve False (y no suma)
    si ya se alcanzó el límite diario configurado.
    """
    hoy = date.today().isoformat()
    with _conexion() as con:
        fila = con.execute(
            "SELECT llamadas FROM uso_api WHERE proveedor = ? AND dia = ?",
            (proveedor, hoy),
        ).fetchone()
        usadas = fila[0] if fila else 0
        if usadas >= limite_diario:
            return False
        con.execute(
            "INSERT OR REPLACE INTO uso_api (proveedor, dia, llamadas) VALUES (?, ?, ?)",
            (proveedor, hoy, usadas + 1),
        )
    return True


def llamadas_hoy(proveedor: str) -> int:
    with _conexion() as con:
        fila = con.execute(
            "SELECT llamadas FROM uso_api WHERE proveedor = ? AND dia = ?",
            (proveedor, date.today().isoformat()),
        ).fetchone()
    return fila[0] if fila else 0
