"""
Junta cada día los precios reales de vuelos (Travelpayouts / Aviasales) desde los
14 orígenes de GlobeWay y los suma a los que ya estaban guardados.

Por qué: Travelpayouts solo entrega precios de búsquedas de los últimos 2 a 7 días.
Guardándolos todos los días, la app tiene precio real para muchos más destinos
(cada uno con la fecha en que se vio; se borran a las 3 semanas o cuando la fecha
del viaje ya pasó).

Lo corre solo GitHub Actions (.github/workflows/precios.yml), una vez al día, y
publica el resultado en la rama "precios" del repo. La app lo lee desde ahí.

Uso manual (desde la carpeta del proyecto, con TRAVELPAYOUTS_TOKEN en el .env):
    python scripts/recolectar_precios.py datos
  → deja los archivos en datos/precios/ (la app los usa si existen; no los subas a main).
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import travelpayouts as tp  # noqa: E402
from servicios.vuelos import ORIGENES  # noqa: E402

MAX_DIAS_VISTO = tp.MAX_DIAS_VISTO
PAUSA = 0.4          # segundos entre consultas, para no saturar la API
MAX_CONSULTAS = 900  # tope de seguridad por día (todas las ciudades de origen)


def tramo_noches(n: int) -> int:
    """Agrupa duraciones parecidas (la app acepta ±3 noches o ±la mitad del viaje)."""
    for i, tope in enumerate((3, 5, 8, 11, 15, 21, 30)):
        if n <= tope:
            return i
    return 7


def consultas(hoy: date) -> list[tuple[str, str, dict, int]]:
    """(nombre, url, parámetros, páginas) que se piden para cada origen."""
    v3 = {"one_way": "false", "direct": "false", "sorting": "price", "currency": "usd", "limit": 1000}
    v2 = {"one_way": "false", "show_to_affiliates": "false", "sorting": "price",
          "currency": "usd", "limit": 1000}
    lista = []
    for m in range(0, 7):   # este mes y los 6 siguientes
        lista.append((f"v3 {tp._mes(hoy, m)}", tp.URL_PRECIOS,
                      {**v3, "departure_at": tp._mes(hoy, m), "return_at": tp._mes(hoy, m),
                       "unique": "false"}, 2))
        lista.append((f"v3 {tp._mes(hoy, m)}→{tp._mes(hoy, m + 1)}", tp.URL_PRECIOS,
                      {**v3, "departure_at": tp._mes(hoy, m), "return_at": tp._mes(hoy, m + 1),
                       "unique": "false"}, 1))
        if m <= 3:   # "unique": una oferta por destino → aparecen destinos poco buscados
            lista.append((f"v3 únicos {tp._mes(hoy, m)}", tp.URL_PRECIOS,
                          {**v3, "departure_at": tp._mes(hoy, m), "return_at": tp._mes(hoy, m + 1),
                           "unique": "true"}, 1))
    lista.append(("v2 año", tp.URL_ULTIMOS, {**v2, "period_type": "year"}, 3))
    for m in range(0, 6):
        lista.append((f"v2 {tp._mes(hoy, m)}", tp.URL_ULTIMOS,
                      {**v2, "period_type": "month", "beginning_of_period": tp._mes(hoy, m) + "-01"}, 1))
    return lista


class SinToken(Exception):
    pass


contador = {"n": 0}


def pedir(url: str, params: dict, token: str) -> list[dict]:
    for intento in range(3):
        if contador["n"] >= MAX_CONSULTAS:
            raise RuntimeError("tope de consultas del día")
        contador["n"] += 1
        time.sleep(PAUSA)
        try:
            return tp._pedir(url, params, token)
        except RuntimeError as e:
            if "token" in str(e):
                raise SinToken(str(e))
            if "esperar" in str(e) and intento < 2:
                time.sleep(20 * (intento + 1))   # la API pidió calma: esperar y reintentar
                continue
            raise
    return []


def recolectar(origen_tp: str, token: str, hoy: date) -> tuple[list[dict], list[str]]:
    ofertas, errores = [], []
    for nombre, url, params, paginas in consultas(hoy):
        fuente = "v3" if url == tp.URL_PRECIOS else "v2"
        try:
            for pagina in range(1, paginas + 1):
                lote = pedir(url, {**params, "origin": origen_tp, "page": pagina}, token)
                ofertas += [n for o in lote if (n := tp._normalizar(fuente, o))]
                if len(lote) < params["limit"]:
                    break
        except SinToken:
            raise
        except Exception as e:   # una consulta que falla no detiene las demás
            errores.append(f"{nombre}: {e}")
    return ofertas, errores


def combinar(viejas: list[dict], nuevas: list[dict], hoy: date) -> list[dict]:
    """Junta lo guardado con lo nuevo y deja solo lo útil (y liviano)."""
    exactas: dict[tuple, dict] = {}
    for o in viejas + nuevas:   # las nuevas van al final: pisan a las viejas del mismo vuelo
        try:
            ida = date.fromisoformat((o.get("departure_at") or "")[:10])
            vuelta = date.fromisoformat((o.get("return_at") or "")[:10])
            visto = date.fromisoformat((o.get("visto") or "")[:10])
        except ValueError:
            continue
        if ida < hoy + timedelta(days=2) or (vuelta - ida).days < 1 or not o.get("price") \
                or not o.get("destination") or (hoy - visto).days > MAX_DIAS_VISTO:
            continue
        k = (o["destination"], o.get("destination_airport") or "", ida, vuelta)
        exactas[k] = o
    # Por destino, mes de salida y duración: la oferta más barata (las recientes valen un poco más)
    grupos: dict[tuple, tuple[float, dict]] = {}
    for (dest, aero, ida, vuelta), o in exactas.items():
        k = (dest, aero, ida.strftime("%Y-%m"), tramo_noches((vuelta - ida).days))
        dias = (hoy - date.fromisoformat(o["visto"][:10])).days
        puntaje = float(o["price"]) * (1 + 0.01 * dias)
        if k not in grupos or puntaje < grupos[k][0]:
            grupos[k] = (puntaje, o)
    return sorted((v[1] for v in grupos.values()),
                  key=lambda o: (o["destination"], o["departure_at"], float(o["price"])))


def main() -> int:
    carpeta = Path(sys.argv[1] if len(sys.argv) > 1 else "datos") / "precios"
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        from servicios import secretos
        secretos.cargar()   # para uso manual con .env
    except Exception:
        pass
    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    if not token:
        print("Falta TRAVELPAYOUTS_TOKEN (en GitHub: Settings → Secrets and variables → Actions).")
        return 1

    hoy = date.today()
    ahora = datetime.now(timezone.utc).isoformat(timespec="minutes")
    ciudad_de, _ = tp._aeropuertos()
    origenes = sorted({ciudad_de.get(o, o) for o in ORIGENES})   # JFK→NYC, EZE→BUE, LHR→LON…
    resumen = {"actualizado": ahora, "origenes": {}}
    for origen_tp in origenes:
        archivo = carpeta / f"{origen_tp}.json.gz"
        viejas = []
        if archivo.exists():
            try:
                viejas = json.loads(gzip.decompress(archivo.read_bytes())).get("ofertas", [])
            except Exception:
                viejas = []
        try:
            nuevas, errores = recolectar(origen_tp, token, hoy)
        except SinToken as e:
            print(f"ERROR: {e}")
            return 1
        for o in nuevas:
            o["visto"] = hoy.isoformat()
        todas = combinar(viejas, nuevas, hoy)
        archivo.write_bytes(gzip.compress(json.dumps(
            {"origen": origen_tp, "actualizado": hoy.isoformat(), "ofertas": todas},
            ensure_ascii=False, separators=(",", ":")).encode(), 9))
        destinos_hoy = len({o["destination"] for o in nuevas})
        destinos = len({o["destination"] for o in todas})
        resumen["origenes"][origen_tp] = {"ciudades_hoy": destinos_hoy, "ciudades_guardadas": destinos,
                                          "ofertas": len(todas), "errores": errores[:5]}
        print(f"{origen_tp}: {destinos_hoy} ciudades hoy · {destinos} guardadas · "
              f"{len(todas)} ofertas · {archivo.stat().st_size / 1024:.0f} KB"
              + (f" · {len(errores)} consultas con error" if errores else ""))
    resumen["consultas"] = contador["n"]
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Listo: {contador['n']} consultas a Travelpayouts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
