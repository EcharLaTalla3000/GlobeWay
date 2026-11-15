"""
Precalcula la red de vuelos (aeropuertos, tramos y rutas más baratas desde los
14 orígenes) y la guarda en datos/red_vuelos.pkl, para que la app cargue más rápido.

Cuándo correrlo: después de cambiar datos/destinos.json, servicios/rutas.py o los
orígenes de servicios/vuelos.py. Si se te olvida, la app igual funciona: detecta
que el archivo no corresponde y arma la red al vuelo (solo tarda un poco más).

Uso (desde la carpeta del proyecto):
    python scripts/precalcular_red.py
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios.costos import RUTA_RED, construir_red, huella_red  # noqa: E402

t = time.time()
red = construir_red(con_rutas=True)
with open(RUTA_RED, "wb") as f:
    pickle.dump({"huella": huella_red(), "red": red}, f, protocol=4)
print(f"Red guardada en {RUTA_RED} ({RUTA_RED.stat().st_size / 1e6:.1f} MB) en {time.time() - t:.1f} s")
