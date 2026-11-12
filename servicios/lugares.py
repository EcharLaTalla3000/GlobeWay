"""
Buscador mundial de ciudades y pueblos (GeoNames).

El globo muestra 1.512 destinos turísticos con datos propios. Este módulo
agrega un buscador con TODAS las ciudades y pueblos del mundo con 1.000
habitantes o más (base abierta GeoNames, licencia CC BY 4.0), para la tabla
de la pestaña "Destinos".

- La lista se descarga sola la primera vez que alguien busca (unos 10 MB) y
  se guarda en datos/lugares.pkl.gz. Si la app se reinicia, se vuelve a bajar.
- Para estos lugares NO hay costos propios: se usan los del país (mediana de
  sus destinos del globo) o, si el país no tiene destinos, los de su región.
  La app siempre lo indica.
"""
from __future__ import annotations

import io
import statistics
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd
import requests

URL_CIUDADES = "https://download.geonames.org/export/dump/cities1000.zip"
URL_PAISES = "https://download.geonames.org/export/dump/countryInfo.txt"
RUTA = Path(__file__).resolve().parent.parent / "datos" / "lugares.pkl.gz"
MAX_RESULTADOS = 300

CAMPOS_COSTO = ("comida", "transporte", "actividades", "hostal", "hotel", "hotel_sup", "depto")

# Códigos ISO3 de GeoNames que en este proyecto (Natural Earth) se escriben distinto
ISO3_PROPIO = {"XKX": "KOS", "PSE": "PSX", "SSD": "SDS", "ESH": "SAH"}

# Nombres en español de países y territorios que no tienen destinos en el globo
# (para el resto se usa el nombre que ya trae datos/destinos.json)
NOMBRES_ES = {
    "SGP": "Singapur", "HKG": "Hong Kong", "MAC": "Macao", "AND": "Andorra", "MCO": "Mónaco",
    "LIE": "Liechtenstein", "SMR": "San Marino", "VAT": "Ciudad del Vaticano", "MLT": "Malta",
    "BHR": "Baréin", "MDV": "Maldivas", "MUS": "Mauricio", "SYC": "Seychelles", "CPV": "Cabo Verde",
    "STP": "Santo Tomé y Príncipe", "COM": "Comoras", "BRB": "Barbados", "ATG": "Antigua y Barbuda",
    "KNA": "San Cristóbal y Nieves", "LCA": "Santa Lucía", "VCT": "San Vicente y las Granadinas",
    "GRD": "Granada", "DMA": "Dominica", "ABW": "Aruba", "CUW": "Curazao", "SXM": "Sint Maarten",
    "MAF": "San Martín (Francia)", "BLM": "San Bartolomé", "GLP": "Guadalupe (Francia)",
    "MTQ": "Martinica (Francia)", "REU": "Reunión (Francia)", "MYT": "Mayotte (Francia)",
    "PYF": "Polinesia Francesa", "WLF": "Wallis y Futuna", "SPM": "San Pedro y Miquelón",
    "BMU": "Bermudas", "CYM": "Islas Caimán", "TCA": "Islas Turcas y Caicos",
    "VGB": "Islas Vírgenes Británicas", "VIR": "Islas Vírgenes de EE. UU.", "AIA": "Anguila",
    "MSR": "Montserrat", "GUM": "Guam", "MNP": "Islas Marianas del Norte", "ASM": "Samoa Americana",
    "WSM": "Samoa", "TON": "Tonga", "KIR": "Kiribati", "TUV": "Tuvalu", "NRU": "Nauru",
    "PLW": "Palaos", "FSM": "Micronesia", "MHL": "Islas Marshall", "COK": "Islas Cook",
    "NIU": "Niue", "FRO": "Islas Feroe", "GIB": "Gibraltar", "IMN": "Isla de Man",
    "JEY": "Jersey", "GGY": "Guernsey", "ALA": "Åland", "SJM": "Svalbard",
    "BES": "Caribe Neerlandés", "SHN": "Santa Elena", "NFK": "Isla Norfolk",
    "CXR": "Isla de Navidad", "CCK": "Islas Cocos", "TKL": "Tokelau", "PCN": "Islas Pitcairn",
    "IOT": "Territorio Británico del Océano Índico", "SGS": "Georgias del Sur",
}

CONTINENTES = {"AF": "África", "AS": "Asia", "EU": "Europa", "NA": "Norteamérica",
               "OC": "Oceanía", "SA": "Sudamérica", "AN": "Antártica"}

_lista: pd.DataFrame | None = None
_paises: dict[str, dict] | None = None
error_carga: str | None = None


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes: 'Chişinău' → 'chisinau'."""
    t = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def _es_latino(nombre: str) -> bool:
    return all(ord(c) < 0x250 or unicodedata.combining(c) for c in nombre)


def _descargar() -> tuple[pd.DataFrame, dict[str, dict]]:
    # Países: ISO2 → ISO3, nombre en inglés y continente
    r = requests.get(URL_PAISES, timeout=30)
    r.raise_for_status()
    paises = {}
    for linea in r.text.splitlines():
        if not linea or linea.startswith("#"):
            continue
        c = linea.split("\t")
        if len(c) > 8:
            iso3 = ISO3_PROPIO.get(c[1], c[1])
            paises[c[0]] = {"iso3": iso3, "nombre": c[4], "continente": c[8]}

    r = requests.get(URL_CIUDADES, timeout=90)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        nombre = [n for n in z.namelist() if n.endswith(".txt")][0]
        with z.open(nombre) as f:
            df = pd.read_csv(f, sep="\t", header=None, quoting=3, dtype=str, keep_default_na=False,
                             usecols=[0, 1, 2, 3, 4, 5, 8, 14],
                             names=["id", "nombre", "ascii", "alternos", "lat", "lon", "pais2", "poblacion"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["poblacion"] = pd.to_numeric(df["poblacion"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["lat", "lon"])

    # Texto de búsqueda: nombre + nombre sin tildes + nombres alternativos en alfabeto latino
    # (ahí vienen "Nueva York", "Londres", "Pekín", etc.)
    def clave(fila) -> str:
        nombres = {normalizar(fila.nombre), normalizar(fila.ascii)}
        for alt in fila.alternos.split(","):
            if alt and len(alt) < 40 and _es_latino(alt):
                nombres.add(normalizar(alt))
        return "|" + "|".join(sorted(n for n in nombres if n)) + "|"

    df["clave"] = [clave(f) for f in df.itertuples(index=False)]
    df["iso3"] = df["pais2"].map(lambda p: paises.get(p, {}).get("iso3", ""))
    df = df.drop(columns=["alternos", "ascii"]).sort_values("poblacion", ascending=False)
    return df.reset_index(drop=True), paises


def cargar() -> pd.DataFrame | None:
    """Devuelve la tabla de lugares (descarga la primera vez). None si no se pudo."""
    global _lista, _paises, error_carga
    if _lista is not None:
        return _lista
    try:
        if RUTA.exists():
            _lista, _paises = pd.read_pickle(RUTA, compression="gzip")
        else:
            _lista, _paises = _descargar()
            try:
                pd.to_pickle((_lista, _paises), RUTA, compression="gzip")
            except Exception:
                pass   # si no se puede guardar, igual funciona en memoria
        error_carga = None
    except Exception as e:
        error_carga = f"{e.__class__.__name__}: {str(e)[:120]}"
        _lista, _paises = None, None
    return _lista


def cantidad() -> int:
    return 0 if _lista is None else len(_lista)


def buscar(texto: str, limite: int = MAX_RESULTADOS) -> pd.DataFrame:
    """Lugares cuyo nombre contiene el texto. Primero coincidencias exactas, luego por población."""
    df = cargar()
    q = normalizar(texto)
    if df is None or len(q) < 2:
        return pd.DataFrame()
    claves = df["clave"]
    hallados = df[claves.str.contains(q, regex=False)]
    if hallados.empty:
        return hallados
    exacto = hallados["clave"].str.contains(f"|{q}|", regex=False)
    inicio = hallados["clave"].str.contains(f"|{q}", regex=False)
    orden = (exacto.astype(int) * 2 + inicio.astype(int))
    hallados = hallados.assign(_orden=orden).sort_values(["_orden", "poblacion"], ascending=[False, False])
    return hallados.head(limite).drop(columns=["_orden"])


# --------------------------------------------------------------------------
# Convertir un lugar de GeoNames en un "destino" que entiende el resto de la app
# --------------------------------------------------------------------------
_bases_cache: tuple | None = None


def _bases(destinos: list[dict]) -> tuple[dict, dict, dict, dict]:
    global _bases_cache
    if _bases_cache is not None:
        return _bases_cache
    por_pais: dict[str, list[dict]] = {}
    for d in destinos:
        por_pais.setdefault(d["iso3"], []).append(d)
    paises = _paises or {}
    cont_de_iso3 = {v["iso3"]: v["continente"] for v in paises.values()}
    def mediana(lista):
        return {k: round(statistics.median(x[k] for x in lista), 1) for k in CAMPOS_COSTO}
    costo_pais = {iso: mediana(l) for iso, l in por_pais.items()}
    por_cont: dict[str, list[dict]] = {}
    for iso, l in por_pais.items():
        por_cont.setdefault(cont_de_iso3.get(iso, "?"), []).extend(l)
    costo_cont = {c: mediana(l) for c, l in por_cont.items()}
    info_pais = {iso: {"pais": l[0]["pais"], "continente": l[0]["continente"],
                       "riesgo": any(x.get("riesgo") for x in l)} for iso, l in por_pais.items()}
    if paises:   # solo se guarda cuando ya se conoce el continente de cada país
        _bases_cache = (costo_pais, costo_cont, info_pais, cont_de_iso3)
    return costo_pais, costo_cont, info_pais, cont_de_iso3


def como_destino(fila, destinos: list[dict]) -> dict:
    """Arma un destino 'extra' con costos estimados del país o de la región."""
    costo_pais, costo_cont, info_pais, cont_de_iso3 = _bases(destinos)
    iso3 = fila.iso3 or ""
    p2 = (_paises or {}).get(fila.pais2, {})
    cont = p2.get("continente") or cont_de_iso3.get(iso3, "?")
    if iso3 in costo_pais:
        costos, base = costo_pais[iso3], "país"
    else:
        costos = costo_cont.get(cont) or next(iter(costo_cont.values()))
        base = "región"
    info = info_pais.get(iso3, {})
    return {
        "id": f"gn{fila.id}", "ciudad": fila.nombre,
        "pais": info.get("pais") or NOMBRES_ES.get(iso3) or p2.get("nombre") or fila.pais2,
        "iso3": iso3, "continente": info.get("continente") or CONTINENTES.get(cont, cont),
        "lat": float(fila.lat), "lon": float(fila.lon), "iata": None, "wiki": fila.nombre,
        "tipo": [], "atractivos": [], "riesgo": bool(info.get("riesgo")),
        "poblacion": int(fila.poblacion), "extra": True, "base_costos": base,
        **costos,
    }
