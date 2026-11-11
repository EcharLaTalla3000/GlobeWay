"""
Genera datos/destinos.json a partir de las listas de datos/ranking/*.txt.

- Mantiene los datos de los destinos que ya existían (costos, aeropuerto,
  atractivos) cuando el nombre coincide.
- Los destinos nuevos heredan los costos promedio estimados de su país.
- Guarda el ranking base (`rank_base`) según el orden de cada lista.

Uso (desde la carpeta del proyecto):
    python scripts/generar_destinos.py
Edita los .txt y vuelve a ejecutarlo para agregar o reordenar destinos.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINOS = RAIZ / "datos" / "destinos.json"
CARPETA = RAIZ / "datos" / "ranking"

# Aeropuertos reales de destinos importantes que no tenían uno asignado.
# Formato: "Nombre en la lista": "IATA". Los destinos sin aeropuerto usan el más
# cercano del país (hasta 250 km) más un traslado terrestre.
AEROPUERTOS = {
    # América
    "Isla de Pascua": "IPC", "Pucón": "ZPC", "Chiloé": "MHC", "Cataratas del Iguazú": "IGR",
    "El Calafate": "FTE", "Ushuaia": "USH", "Salta": "SLA", "Córdoba": "COR", "Puerto Madryn": "REL",
    "Arequipa": "AQP", "Lago Titicaca (Puno)": "JUL", "Iquitos": "IQT", "Salar de Uyuni": "UYU",
    "Sucre": "SRE", "Santa Cruz de la Sierra": "VVI", "Islas Galápagos": "GPS", "Guayaquil": "GYE",
    "Cuenca": "CUE", "Punta del Este": "PDP", "Santa Marta": "SMR", "San Andrés": "ADZ", "Cali": "CLO",
    "Bogotá": "BOG", "Isla de Margarita": "PMV", "Los Roques": "LRV", "Tulum": "TQO", "Los Cabos": "SJD",
    "Puerto Vallarta": "PVR", "Oaxaca": "OAX", "Varadero": "VRA", "Santiago de Cuba": "SCU",
    "Cayo Coco": "CCC", "Puerto Plata": "POP", "Península de Samaná": "AZS", "La Romana": "LRM",
    "Santo Domingo": "SDQ", "Bocas del Toro": "BOC", "Volcán Arenal": "LIR", "Tamarindo": "LIR",
    "Liberia": "LIR", "Tikal": "FRS", "Flores": "FRS", "Las Vegas": "LAS", "Orlando": "MCO",
    "San Francisco": "SFO", "Washington D. C.": "IAD", "Honolulu (Hawái)": "HNL", "Chicago": "ORD",
    "Nueva Orleans": "MSY", "Boston": "BOS", "San Diego": "SAN", "Seattle": "SEA", "Maui": "OGG",
    "Nashville": "BNA", "Anchorage (Alaska)": "ANC", "Gran Cañón": "FLG", "Montreal": "YUL",
    "Quebec": "YQB", "Calgary": "YYC", "Ottawa": "YOW", "Halifax": "YHZ", "Victoria": "YYJ",
    "Salvador de Bahía": "SSA", "Foz do Iguaçu": "IGU", "Fernando de Noronha": "FEN", "Recife": "REC",
    "Fortaleza": "FOR", "Manaos (Amazonas)": "MAO", "Brasilia": "BSB", "Ilulissat": "JAV",
    "Kangerlussuaq": "SFJ", "Tobago": "TAB", "Exuma": "GGT",
    # Europa
    "Sevilla": "SVQ", "Palma de Mallorca": "PMI", "Málaga": "AGP", "Valencia": "VLC", "Tenerife": "TFS",
    "Ibiza": "IBZ", "Granada": "GRX", "Oporto": "OPO", "Algarve (Lagos)": "FAO", "Madeira": "FNC",
    "Azores": "PDL", "Niza": "NCE", "Marsella": "MRS", "Lyon": "LYS", "Burdeos": "BOD", "Venecia": "VCE",
    "Milán": "MXP", "Nápoles": "NAP", "Pisa": "PSA", "Taormina (Sicilia)": "CTA", "Edimburgo": "EDI",
    "Manchester": "MAN", "Múnich": "MUC", "Hamburgo": "HAM", "Ginebra": "GVA", "Salzburgo": "SZG",
    "Innsbruck": "INN", "Santorini": "JTR", "Mykonos": "JMK", "Creta": "HER", "Rodas": "RHO",
    "Corfú": "CFU", "Split": "SPU", "Zagreb": "ZAG", "Varsovia": "WAW", "Gdańsk": "GDN", "Bergen": "BGO",
    "Tromsø": "TOS", "Gotemburgo": "GOT", "Rovaniemi": "RVN", "Antalya": "AYT", "Capadocia": "NAV",
    "Bodrum": "BJV", "Esmirna": "ADB", "Ankara": "ESB", "San Petersburgo": "LED", "Sochi": "AER",
    "Kazán": "KZN", "Vladivostok": "VVO", "Lago Baikal": "IKT", "Ekaterimburgo": "SVX",
    "Kaliningrado": "KGD", "Kamchatka": "PKC", "Múrmansk": "MMK", "Yakutsk": "YKS", "Akureyri": "AEY",
    # Asia y Oceanía
    "Shanghái": "PVG", "Xi'an": "XIY", "Guilin": "KWL", "Chengdú": "CTU", "Hangzhou": "HGH",
    "Lhasa": "LXA", "Lijiang": "LJG", "Sanya (Hainan)": "SYX", "Harbin": "HRB", "Macao": "MFM",
    "Chongqing": "CKG", "Zhangjiajie": "DYG", "Dunhuang": "DNH", "Osaka": "KIX", "Hiroshima": "HIJ",
    "Sapporo (Hokkaido)": "CTS", "Okinawa": "OKA", "Busan": "PUS", "Isla de Jeju": "CJU",
    "Ciudad Ho Chi Minh": "SGN", "Da Nang": "DAD", "Hue": "HUI", "Phu Quoc": "PQC", "Nha Trang": "CXR",
    "Chiang Mai": "CNX", "Krabi": "KBV", "Ko Samui": "USM", "Chiang Rai": "CEI", "Phnom Penh": "PNH",
    "Vientiane": "VTE", "Bagan": "NYU", "Mandalay": "MDL", "Lago Inle": "HEH", "George Town (Penang)": "PEN",
    "Langkawi": "LGK", "Kota Kinabalu": "BKI", "Yakarta": "CGK", "Yogyakarta": "YIA", "Lombok": "LOP",
    "Komodo": "LBJ", "Manila": "MNL", "Boracay": "MPH", "Puerto Princesa": "PPS", "Bohol": "TAG",
    "El Nido (Palawan)": "ENI", "Siargao": "IAO", "Goa": "GOI", "Jaipur": "JAI", "Varanasi": "VNS",
    "Kerala (Alappuzha)": "COK", "Udaipur": "UDR", "Amritsar": "ATQ", "Pokhara": "PKR",
    "Islamabad": "ISB", "Karachi": "KHI", "Skardu": "KDU", "Shiraz": "SYZ", "Isfahán": "IFN",
    "Mashhad": "MHD", "Bagdad": "BGW", "Basora": "BSR", "Áqaba": "AQJ", "Eilat": "ETM", "Yeda": "JED",
    "Medina": "MED", "AlUla": "ULH", "Abu Dabi": "AUH", "Salalah": "SLL", "Astaná": "NQZ",
    "Taskent": "TAS", "Bujará": "BHK", "Osh": "OSS", "Batumi": "BUS", "Kutaisi": "KUT",
    "Melbourne": "MEL", "Gran Barrera de Coral (Cairns)": "CNS", "Uluru": "AYQ", "Gold Coast": "OOL",
    "Brisbane": "BNE", "Perth": "PER", "Hobart (Tasmania)": "HBA", "Islas Whitsunday": "PPP",
    "Christchurch": "CHC", "Wellington": "WLG", "Rotorua": "ROT", "Suva": "SUV",
    # África
    "Luxor": "LXR", "Sharm el-Sheij": "SSH", "Hurghada": "HRG", "Asuán": "ASW", "Abu Simbel": "ABS",
    "Fez": "FEZ", "Tánger": "TNG", "Agadir": "AGA", "Esauira": "ESU", "Yerba": "DJE", "Orán": "ORN",
    "Mombasa": "MBA", "Zanzíbar": "ZNZ", "Kilimanjaro": "JRO", "Dar es-Salam": "DAR", "Abuja": "ABV",
    "Durban": "DUR", "Parque Nacional Kruger": "MQP", "Gqeberha": "PLZ", "Swakopmund": "WVB",
    "Kasane": "BBK", "Nosy Be": "NOS", "Lalibela": "LLI", "Gondar": "GDQ", "Bahir Dar": "BJR",
}

COSTOS = ["comida", "transporte", "actividades", "hostal", "hotel", "hotel_sup", "depto"]

PALABRAS_TIPO = [
    ("naturaleza", r"parque|monte|volc|lago|ca[ñn][oó]n|catarata|valle|desierto|glaciar|reserva|"
                   r"bosque|salar|fiordo|cascada|montañ|delta|sabana|geysir|selva|r[ií]o |cueva|"
                   r"meseta|salinas|pantano|garganta|paso de|kilimanjaro|serengeti|everest|uluru"),
    ("playa", r"isla|playa|bah[ií]a|cayo|costa|beach|archipi|pen[ií]nsula|laguna|islas|riviera"),
    ("historia", r"castillo|abad[ií]a|monasterio|pir[aá]mide|ruina|templo|mezquita|ciudadela|"
                 r"palacio|fuerte|minarete|tiwanaku|machu|angkor|petra|[eé]feso|pompeya|tikal|"
                 r"chich[eé]n|babilonia|persépolis|palmira|meroe|bagan|borobudur|auschwitz"),
]


def normalizar(texto: str) -> str:
    texto = texto.split(" (")[0].split(" /")[0]
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def slug(texto: str) -> str:
    return normalizar(texto).replace(" ", "_")[:40]


def tipos_por_nombre(nombre: str) -> list[str]:
    n = nombre.lower()
    tipos = [t for t, patron in PALABRAS_TIPO if re.search(patron, n)]
    return tipos or ["ciudad", "cultura"]


def leer_listas() -> dict[str, list[dict]]:
    por_pais: dict[str, list[dict]] = defaultdict(list)
    for archivo in sorted(CARPETA.glob("*.txt")):
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            partes = linea.split("|")
            iso, nombre, lat, lon = partes[:4]
            wiki = partes[4] if len(partes) > 4 and partes[4] else nombre
            por_pais[iso].append({"nombre": nombre, "lat": float(lat), "lon": float(lon), "wiki": wiki})
    return por_pais


def main() -> None:
    datos = json.loads(DESTINOS.read_text(encoding="utf-8"))
    actuales = datos["destinos"]
    por_pais_actual: dict[str, list[dict]] = defaultdict(list)
    for d in actuales:
        por_pais_actual[d["iso3"]].append(d)

    listas = leer_listas()
    salida: list[dict] = []
    ids_usados: set[str] = set()

    for iso in list(por_pais_actual) + [i for i in listas if i not in por_pais_actual]:
        existentes = por_pais_actual.get(iso, [])
        if not existentes:
            print(f"Aviso: {iso} no tiene datos de costo; se omite.")
            continue
        base = existentes[0]
        ref = {k: round(sum(e[k] for e in existentes) / len(existentes)) for k in COSTOS}
        riesgo = any(e.get("riesgo") for e in existentes)
        usados: set[int] = set()

        for rank, fila in enumerate(listas.get(iso, []), start=1):
            clave = normalizar(fila["nombre"])
            match = None
            for i, e in enumerate(existentes):
                if i in usados:
                    continue
                if clave in (normalizar(e["ciudad"]), normalizar(e.get("wiki", ""))):
                    match = i
                    break
            if match is not None:
                usados.add(match)
                e = existentes[match]
                nuevo = dict(e)
                if e["ciudad"] != fila["nombre"]:
                    nuevo["atractivos"] = []   # el destino antiguo agrupaba varios lugares
                nuevo.update(ciudad=fila["nombre"], lat=fila["lat"], lon=fila["lon"], wiki=fila["wiki"])
            else:
                nuevo = {
                    "id": f"{iso.lower()}_{slug(fila['nombre'])}",
                    "ciudad": fila["nombre"], "pais": base["pais"], "iso3": iso,
                    "continente": base["continente"], "lat": fila["lat"], "lon": fila["lon"],
                    "iata": None, "wiki": fila["wiki"], "tipo": tipos_por_nombre(fila["nombre"]),
                    **ref, "atractivos": [],
                }
                if riesgo:
                    nuevo["riesgo"] = True
            if not nuevo.get("iata") and fila["nombre"] in AEROPUERTOS:
                nuevo["iata"] = AEROPUERTOS[fila["nombre"]]
            nuevo["rank_base"] = rank
            while nuevo["id"] in ids_usados:
                nuevo["id"] += "_2"
            ids_usados.add(nuevo["id"])
            salida.append(nuevo)

        # Destinos antiguos que no aparecen en la lista: se conservan al final
        siguiente = len(listas.get(iso, [])) + 1
        for i, e in enumerate(existentes):
            if i not in usados:
                nuevo = dict(e, rank_base=siguiente)
                siguiente += 1
                ids_usados.add(nuevo["id"])
                salida.append(nuevo)

    datos["destinos"] = salida
    datos["_aviso"] = ("DATOS DE DEMOSTRACIÓN. Costos en USD aproximados (estimación manual). "
                       "'rank_base' es el ranking turístico base de cada país, compilado "
                       "manualmente; la app lo actualiza con visitas a Wikipedia cuando hay conexión. "
                       "'riesgo' marca países con advertencias de seguridad (referencial).")
    # Un destino por línea: liviano y fácil de revisar
    lineas = ['{"_aviso": ' + json.dumps(datos["_aviso"], ensure_ascii=False) + ",",
              ' "_campos": ' + json.dumps(datos.get("_campos", {}), ensure_ascii=False) + ",",
              ' "destinos": [']
    lineas += ["  " + json.dumps(x, ensure_ascii=False, separators=(",", ":"))
               + ("," if i < len(salida) - 1 else "") for i, x in enumerate(salida)]
    lineas.append(" ]}")
    DESTINOS.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{len(salida)} destinos en {len({d['iso3'] for d in salida})} países")


if __name__ == "__main__":
    main()
