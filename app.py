"""
GLOBEWAY — app principal (Streamlit)

¿Con cuánto dinero cuento, desde dónde quiero viajar y a qué lugares del mundo
puedo ir con ese presupuesto?

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from componentes.globo import mostrar_globo
from componentes.portada import logo_mini, mostrar_portada
from servicios import (alojamientos, info_destino, lugares, secretos, tipos_cambio, travelpayouts,
                       turismo, vuelos)
from servicios.costos import (ESTADOS, ESTADOS_GENERALES, TIPOS_ALOJAMIENTO, calcular,
                              cargar_destinos, estado_presupuesto, estados_cuartiles)

secretos.cargar()  # claves desde variables de entorno, .env o Secrets de Streamlit Cloud

_ICONO = Path(__file__).parent / "componentes" / "logo_gw.png"
st.set_page_config(page_title="GlobeWay", page_icon=str(_ICONO) if _ICONO.exists() else "🌍",
                   layout="wide", initial_sidebar_state="expanded")

# --------------------------------------------------------------------------
# Estilos
# --------------------------------------------------------------------------
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"], .stMarkdown, .stText { font-family: 'Inter', system-ui, sans-serif; }
  .block-container { padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1400px; }
  section[data-testid="stSidebar"] { background: #0a0e18; border-right: 1px solid rgba(148,163,184,.12); }
  .marca { font-size: 1.65rem; font-weight: 700; letter-spacing: -.02em; margin: 0; }
  .marca span { color: #f5a524; }
  .bajada { color: #94a3b8; margin: .1rem 0 1rem; font-size: .95rem; }
  .kpi { background: #0d1220; border: 1px solid rgba(148,163,184,.14); border-radius: 12px;
         padding: .8rem 1rem; }
  .kpi .n { font-size: 1.6rem; font-weight: 700; line-height: 1.1; }
  .kpi .t { color: #94a3b8; font-size: .8rem; margin-top: .2rem; }
  .aviso-demo { background: rgba(251,191,36,.08); border: 1px solid rgba(251,191,36,.3);
         color: #fcd34d; border-radius: 10px; padding: .55rem .9rem; font-size: .85rem; margin-bottom: .8rem; }
  .etq { display:inline-block; font-size:.72rem; padding:.12rem .55rem; border-radius:999px;
         border:1px solid currentColor; font-weight:600; }
  div[data-testid="stTabs"] button p { font-size: .95rem; }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Script "Drive" de Travelpayouts (lo exige su registro para verificar el sitio).
# Streamlit no deja editar el <head>, así que se agrega desde un iframe invisible
# a la página principal. Va antes de la portada para que esté en todas las vistas.
# --------------------------------------------------------------------------
TP_DRIVE_SRC = "https://emrldtp.com/NTk5NTYy.js?t=599562"
components.html(f"""<script>
(function () {{
  function poner(doc) {{
    if (!doc || doc.getElementById('tp-drive')) return true;
    var s = doc.createElement('script');
    s.id = 'tp-drive'; s.async = 1; s.setAttribute('data-cmp-ab', '2');
    s.src = '{TP_DRIVE_SRC}';
    doc.head.appendChild(s);
    return true;
  }}
  try {{ poner(window.top.document); }} catch (e) {{
    try {{ poner(window.parent.document); }} catch (e2) {{}}
  }}
}})();
</script>""", height=0)
st.markdown("<style>iframe[height='0']{display:block;margin:0}"
            "div[data-testid='stElementContainer']:has(iframe[height='0'])"
            "{height:0;min-height:0;overflow:hidden;margin:0;padding:0}</style>",
            unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Portada animada: se muestra hasta que la persona aprieta "Iniciar"
# --------------------------------------------------------------------------
if not st.session_state.get("iniciado"):
    mostrar_portada()   # detiene la app aquí (st.stop) mientras no se aprieta el botón


# --------------------------------------------------------------------------
# Datos con caché de Streamlit
# --------------------------------------------------------------------------
def _tasas():
    # Sin st.cache_data: así un fallo no queda "pegado" una hora.
    # La caché real (6 h, solo para respuestas buenas) está en servicios/cache.py
    return tipos_cambio.obtener_tasas()


@st.cache_data
def _destinos():
    return cargar_destinos()


def _wiki(titulo: str):
    # La caché (7 días, solo resultados exitosos) está en servicios/cache.py
    return info_destino.resumen(titulo)


tasas = _tasas()
DESTINOS = _destinos()
TIPOS_TURISMO = sorted({t for d in DESTINOS for t in d["tipo"]})


# --------------------------------------------------------------------------
# Panel lateral: parámetros del viaje
# --------------------------------------------------------------------------
with st.sidebar:
    # ---- Interruptor principal ----
    generales = st.toggle(
        "Precios generales", value=False,
        help="Colorea el mapa según lo caro o barato de cada destino comparado con el "
             "resto del mundo, sin necesidad de ingresar un presupuesto.")
    turisticos = st.toggle(
        "Más turísticos", value=False,
        help="Muestra un mapa de calor de las zonas más visitadas del mundo. Con conexión, "
             "el ranking se actualiza con las visitas recientes a cada destino en Wikipedia.")
    if turisticos and generales:
        st.caption("El mapa muestra «Más turísticos»; «Precios generales» se aplica a las tablas.")

    st.markdown("### Tu viaje")
    moneda = st.selectbox("Moneda", list(tipos_cambio.MONEDAS),
                          format_func=lambda m: f"{m} · {tipos_cambio.MONEDAS[m]['nombre']}")
    paso = 50_000 if moneda == "CLP" else 50
    if generales or turisticos:
        presupuesto = 0
    else:
        por_defecto = {"CLP": 2_000_000, "USD": 2_000, "EUR": 1_900}.get(moneda, 2000)
        presupuesto = st.number_input(f"Presupuesto total ({moneda})", min_value=0,
                                      value=por_defecto, step=paso)

    origen = st.selectbox("Desde dónde viajas", list(vuelos.ORIGENES),
                          format_func=lambda c: vuelos.ORIGENES[c]["nombre"])

    usar_fechas = st.toggle("Tengo fechas definidas", value=False)
    if usar_fechas:
        hoy = date.today()
        rango = st.date_input("Fechas (ida – vuelta)",
                              value=(hoy + timedelta(days=30), hoy + timedelta(days=37)),
                              min_value=hoy, format="DD/MM/YYYY")
        if isinstance(rango, tuple) and len(rango) == 2 and rango[1] > rango[0]:
            llegada, salida = rango
        else:
            llegada, salida = hoy + timedelta(days=30), hoy + timedelta(days=37)
            st.caption("Elige fecha de ida y de vuelta.")
        dias = (salida - llegada).days + 1
        st.caption(f"{dias} días · {dias - 1} noches")
    else:
        llegada = salida = None
        dias = st.slider("Duración (días)", 2, 30, 8)

    viajeros = st.number_input("Viajeros", 1, 10, 2)
    tipo_aloj = st.selectbox("Alojamiento", list(TIPOS_ALOJAMIENTO), index=1,
                             format_func=lambda t: TIPOS_ALOJAMIENTO[t])

    st.markdown("### Vista del mapa")
    if generales:
        base_general = st.radio(
            "Comparar según", ["total", "vida"],
            format_func=lambda m: "Costo total del viaje (con vuelos desde tu origen)"
            if m == "total" else "Costo de vida en destino (sin vuelos)")
    else:
        base_general = "total"
    filtro_tipo = st.multiselect("Tipo de turismo", TIPOS_TURISMO,
                                 format_func=str.capitalize, placeholder="Todos")
    ocultar_fuera = (not generales and not turisticos) and st.checkbox(
        "Ocultar destinos fuera de presupuesto", value=False)
    ocultar_riesgo = st.checkbox("Ocultar países con advertencias de seguridad", value=False)

    st.divider()
    st.caption("**Tipo de cambio:** " + tasas.fuente +
               (f" · actualizado {tasas.actualizado.astimezone().strftime('%d/%m/%Y %H:%M')}"
                if tasas.actualizado else ""))
    if tasas.es_respaldo:
        st.warning("No se pudo obtener el tipo de cambio en línea; se usan tasas fijas "
                   "aproximadas. Detalle: " + tasas.fuente.split("Motivo: ")[-1], icon="⚠️")
        if st.button("Reintentar tipo de cambio"):
            st.rerun()
    else:
        st.caption(" · ".join(f"1 USD = {tipos_cambio.formatear(tasas.por_usd[m], m)}"
                              for m in tipos_cambio.MONEDAS if m != "USD"))


# --------------------------------------------------------------------------
# Cálculo para todos los destinos
# --------------------------------------------------------------------------
def fmt(usd: float) -> str:
    """Convierte un monto en USD a la moneda elegida y lo formatea."""
    return tipos_cambio.formatear(tipos_cambio.convertir(usd, moneda, tasas), moneda)


presupuesto_usd = tipos_cambio.a_usd(presupuesto, moneda, tasas)
noches = max(dias - 1, 1)

# Precios reales de vuelos (Travelpayouts / Aviasales), si hay token configurado.
# Una sola consulta por origen y fechas; se guarda 6 horas en caché.
precios_tp = None
if travelpayouts.configurado():
    with st.spinner("Buscando precios reales de vuelos…"):
        precios_tp = travelpayouts.obtener_precios(origen, llegada, salida, noches)

# Ranking turístico: visitas en Wikipedia (en vivo) o ranking base (sin conexión)
with st.spinner("Actualizando ranking turístico…"):
    popularidad = turismo.obtener_popularidad(DESTINOS)
RANKING = turismo.calcular_ranking(DESTINOS, popularidad)

filas = []
for d in DESTINOS:
    if filtro_tipo and not set(filtro_tipo) & set(d["tipo"]):
        continue
    if ocultar_riesgo and d.get("riesgo"):
        continue
    c = calcular(d, origen, dias, viajeros, tipo_aloj, precios_tp)
    filas.append({**d, "calc": c, "estado": estado_presupuesto(c.total, presupuesto_usd)})


def metrica(f: dict) -> float:
    """Valor que define el color en modo Precios generales."""
    return f["calc"].total if base_general == "total" else f["calc"].diario_pp


for f in filas:
    f.update(RANKING[f["id"]])   # rank, visitas, peso

ESTADOS_TURISMO = [
    ("t1", "Menos visitado", "#38bdf8"),
    ("t2", "Visitado", "#a3e635"),
    ("t3", "Muy visitado", "#fb923c"),
    ("t4", "De los más visitados", "#ef4444"),
]
paises_turismo = {}
if turisticos:
    estados, _ = estados_cuartiles([f["peso"] for f in filas])
    a_turismo = {k: t[0] for k, t in zip(("economico", "intermedio", "costoso", "fuera"), ESTADOS_TURISMO)}
    for f, e in zip(filas, estados):
        f["estado"] = a_turismo[e]
    # Color de cada país según sus llegadas internacionales (cuartiles entre países)
    isos = sorted({f["iso3"] for f in filas})
    est_p, _ = estados_cuartiles([turismo.LLEGADAS.get(i, 0.05) for i in isos])
    paises_turismo = {i: a_turismo[e] for i, e in zip(isos, est_p)}
elif generales:
    estados, cortes = estados_cuartiles([metrica(f) for f in filas])
    for f, e in zip(filas, estados):
        f["estado"] = e
elif ocultar_fuera:
    filas = [f for f in filas if f["estado"] != "fuera"]

if turisticos:
    filas.sort(key=lambda f: -f["peso"])
else:
    filas.sort(key=lambda f: f["calc"].total)

if turisticos:
    colores = {k: c for k, _, c in ESTADOS_TURISMO}
    textos = {k: t for k, t, _ in ESTADOS_TURISMO}
    leyenda = [{"etiqueta": t, "color": c} for _, t, c in ESTADOS_TURISMO]
    titulo_leyenda = ("Más turísticos · Wikipedia en vivo" if popularidad.en_vivo
                      else "Más turísticos · ranking base")
elif generales:
    colores = {k: c for k, _, c in ESTADOS_GENERALES}
    textos = {k: t for k, t, _ in ESTADOS_GENERALES}
    sufijo = "" if base_general == "total" else " p/p/día"
    if cortes:
        rangos = [f"hasta {fmt(cortes[0])}", f"{fmt(cortes[0])} – {fmt(cortes[1])}",
                  f"{fmt(cortes[1])} – {fmt(cortes[2])}", f"más de {fmt(cortes[2])}"]
    else:
        rangos = [""] * 4
    leyenda = [{"etiqueta": f"{t} ({r}{sufijo})", "color": c}
               for (_, t, c), r in zip(ESTADOS_GENERALES, rangos)]
    titulo_leyenda = ("Precios generales · viaje total" if base_general == "total"
                      else "Precios generales · costo de vida")
else:
    colores = {k: v["color"] for k, v in ESTADOS.items()}
    textos = {k: v["etiqueta"] for k, v in ESTADOS.items()}
    leyenda = [{"etiqueta": v["etiqueta"], "color": v["color"]} for v in ESTADOS.values()]
    titulo_leyenda = f"Viaje total vs. {fmt(presupuesto_usd)}"

def texto_vuelo_real(r) -> str:
    """Fechas, escalas y aerolínea de un precio real (para el globo y las tablas)."""
    partes = [r.fechas_txt() + (" (fechas cercanas a las tuyas)" if r.fechas_cercanas else ""),
              r.escalas_txt()]
    if r.aerolinea:
        partes.append(f"aerolínea {r.aerolinea}")
    return " · ".join(partes)


colores.setdefault("sin_datos", "#64748b")
textos.setdefault("sin_datos", "Sin datos turísticos")

max_metrica = max((metrica(f) for f in filas), default=1) or 1
datos_globo = {
    "modo": "turismo" if turisticos else ("general" if generales else "presupuesto"),
    "paises": paises_turismo,
    "llegadas": {i: turismo.LLEGADAS.get(i) for i in {f["iso3"] for f in filas}},
    "colores": colores,
    "leyenda": leyenda,
    "titulo_leyenda": titulo_leyenda,
    "viajeros": int(viajeros),
    "noches": noches,
    "resumen": f"{viajeros} viajero{'s' if viajeros > 1 else ''}, {dias} días, desde {origen}",
    "origen": {"codigo": origen, **{k: vuelos.ORIGENES[origen][k] for k in ("lat", "lon")}},
    "destinos": [{
        "id": f["id"], "ciudad": f["ciudad"], "pais": f["pais"], "iso3": f["iso3"],
        "continente": f["continente"], "lat": f["lat"], "lon": f["lon"],
        "atractivos": f["atractivos"], "riesgo": bool(f.get("riesgo")),
        "estado": f["estado"], "estado_txt": textos[f["estado"]],
        "total_usd": f["calc"].total,
        "total_rel": (f["calc"].total / presupuesto_usd
                      if not generales and not turisticos and presupuesto_usd
                      else metrica(f) / max_metrica),
        "rank": f["rank"], "visitas": f["visitas"], "peso": round(f["peso"], 4),
        "total_fmt": fmt(f["calc"].total),
        "vuelo_pp_fmt": fmt(f["calc"].vuelo_pp),
        "vuelo_real": bool(f["calc"].vuelo_real),
        "vuelo_real_txt": texto_vuelo_real(f["calc"].vuelo_real) if f["calc"].vuelo_real else "",
        "vuelo_link": f["calc"].vuelo_real.enlace(int(viajeros)) if f["calc"].vuelo_real else "",
        "diario_fmt": fmt(f["calc"].diario_pp),
        "distancia_km": f["calc"].distancia_km,
        "ruta_txt": f["calc"].ruta.texto(),
        "ruta": [{"c": et, "lat": la, "lon": lo}
                 for et, (la, lo) in zip(f["calc"].ruta.etiquetas, f["calc"].ruta.coords)],
        "fmt": {k: fmt(getattr(f["calc"], k))
                for k in ("vuelos", "alojamiento", "comida", "transporte", "actividades")},
    } for f in filas],
}


# --------------------------------------------------------------------------
# Encabezado e indicadores
# --------------------------------------------------------------------------
st.markdown(f'<p class="marca">{logo_mini(30)}Globe<span>Way</span></p>', unsafe_allow_html=True)
if turisticos:
    st.markdown('<p class="bajada"><b>Más turísticos</b>: zonas más visitadas del mundo. '
                'Usa <b>Ver destinos</b> (a la derecha del globo) para mostrar las columnas de turistas. '
                + ('Ranking actualizado con visitas a Wikipedia de los últimos 30 días.'
                   if popularidad.en_vivo else
                   'Sin conexión a Wikipedia: se muestra el ranking base.') + '</p>',
                unsafe_allow_html=True)
elif generales:
    st.markdown(f'<p class="bajada"><b>Precios generales</b>: qué tan caro es cada destino '
                f'comparado con el resto del mundo · desde <b>{vuelos.ORIGENES[origen]["nombre"]}</b>, '
                f'{viajeros} viajero{"s" if viajeros > 1 else ""}, {dias} días.</p>',
                unsafe_allow_html=True)
else:
    st.markdown(f'<p class="bajada">Con <b>{fmt(presupuesto_usd)}</b>, saliendo desde '
                f'<b>{vuelos.ORIGENES[origen]["nombre"]}</b>, {viajeros} viajero'
                f'{"s" if viajeros > 1 else ""} y {dias} días: ¿a dónde puedes ir?</p>',
                unsafe_allow_html=True)
n_reales = sum(1 for f in filas if f["calc"].vuelo_real)
if precios_tp is not None and n_reales:
    st.markdown('<div class="aviso-demo">⚠ <b>Modo demostración parcial.</b> '
                f'<b>{n_reales} de {len(filas)} destinos</b> usan el <b>precio real de búsquedas '
                'recientes</b> del vuelo (Aviasales, ✈). El resto de los vuelos, el costo de vida y '
                'los alojamientos son <b>estimaciones de ejemplo</b>. El tipo de cambio sí es real.</div>',
                unsafe_allow_html=True)
else:
    st.markdown('<div class="aviso-demo">⚠ <b>Modo demostración.</b> Los costos de vida, vuelos y '
                'alojamientos son <b>estimaciones de ejemplo</b>, no tarifas reales. '
                'El tipo de cambio sí es real cuando hay conexión.</div>', unsafe_allow_html=True)
    if precios_tp is not None and precios_tp.error:
        st.caption(f"No se pudieron obtener precios reales de vuelos: {precios_tp.error}.")

conteo = pd.Series([f["estado"] for f in filas]).value_counts() if filas else pd.Series(dtype=int)
cols = st.columns(4)
if turisticos:
    top = filas[0] if filas else None
    top_pais = max({f["iso3"] for f in filas}, key=lambda i: turismo.LLEGADAS.get(i, 0)) if filas else None
    nombre_pais = next((f["pais"] for f in filas if f["iso3"] == top_pais), "—")
    indicadores = [
        ("En vivo" if popularidad.en_vivo else "Base",
         "ranking por visitas a Wikipedia (30 días)" if popularidad.en_vivo
         else "ranking base (sin conexión a Wikipedia)",
         "#34d399" if popularidad.en_vivo else "#facc15"),
        (top["ciudad"] if top else "—", "zona más visitada (estimación)", "#ef4444"),
        (nombre_pais, f"país con más turistas (~{turismo.LLEGADAS.get(top_pais, 0):g} M/año)", "#fb923c"),
        (len(filas), f"destinos en {len({f['iso3'] for f in filas})} países", "#e5e9f0"),
    ]
elif generales:
    valores = sorted(metrica(f) for f in filas)
    barato = min(filas, key=metrica) if filas else None
    caro = max(filas, key=metrica) if filas else None
    sufijo = "" if base_general == "total" else " / día"
    indicadores = [
        (len(filas), f"destinos en {len({f['iso3'] for f in filas})} países", "#e5e9f0"),
        (fmt(metrica(barato)) + sufijo if barato else "—",
         f"más barato: {barato['ciudad']}" if barato else "", "#34d399"),
        (fmt(valores[len(valores) // 2]) + sufijo if valores else "—", "valor típico (mediana)", "#facc15"),
        (fmt(metrica(caro)) + sufijo if caro else "—",
         f"más caro: {caro['ciudad']}" if caro else "", "#ef4444"),
    ]
else:
    dentro = int(sum(conteo.get(k, 0) for k in ("economico", "intermedio", "costoso")))
    indicadores = [
        (dentro, "destinos dentro del presupuesto", "#34d399"),
        (int(conteo.get("ligeramente_sobre", 0)), "ligeramente sobre (hasta +15%)", "#a78bfa"),
        (int(conteo.get("fuera", 0)), "fuera de presupuesto", "#ef4444"),
        (fmt(filas[0]["calc"].total) if filas else "—",
         f"opción más barata: {filas[0]['ciudad']}" if filas else "sin destinos", "#e5e9f0"),
    ]
for col, (n, t, c) in zip(cols, indicadores):
    col.markdown(f'<div class="kpi"><div class="n" style="color:{c}">{n}</div>'
                 f'<div class="t">{t}</div></div>', unsafe_allow_html=True)

st.write("")
mostrar_globo(datos_globo, alto=640)


# --------------------------------------------------------------------------
# Pestañas inferiores
# --------------------------------------------------------------------------
tab_lista, tab_explorar, tab_aloj, tab_fuentes = st.tabs(
    ["Destinos", "Explorar destino", "Alojamientos", "Datos y fuentes"])

opciones_ids = [f["id"] for f in filas]
por_id = {f["id"]: f for f in filas}
etiqueta_dest = lambda i: f"{por_id[i]['ciudad']} · {por_id[i]['pais']} — {fmt(por_id[i]['calc'].total)}"

# ---- Ranking y buscador ----
def fila_tabla(f: dict) -> dict:
    c, r = f["calc"], f["calc"].vuelo_real
    return {
        "Destino": f["ciudad"], "País": f["pais"],
        "En el globo": "No (buscador)" if f.get("extra") else "Sí",
        "Población": f.get("poblacion"),
        "Ranking en su país": f.get("rank"),
        "Visitas Wikipedia (30 días)": f.get("visitas"),
        "Estado": textos[f["estado"]],
        f"Total viaje ({moneda})": round(tipos_cambio.convertir(c.total, moneda, tasas)),
        f"Vuelo p/p ({moneda})": round(tipos_cambio.convertir(c.vuelo_pp, moneda, tasas)),
        "Precio del vuelo": "✈ Real (búsquedas recientes)" if r else "Estimado",
        "Ruta": (f"{r.aeropuerto_origen} → {r.aeropuerto_destino} · {r.fechas_txt()}"
                 + (" (fechas cercanas)" if r.fechas_cercanas else "")) if r
                else c.ruta.recorrido() + (f" + {round(c.ruta.traslado_km)} km de traslado"
                                           if f.get("extra") and c.ruta.traslado_km >= 30 else ""),
        "Escalas": r.escalas_ida if r else c.ruta.escalas,
        f"Costo de vida p/p/día ({moneda})": round(tipos_cambio.convertir(c.diario_pp, moneda, tasas)),
        "% del presupuesto": (c.total / presupuesto_usd * 100) if presupuesto_usd else None,
        "Alerta": "⚠️" if f.get("riesgo") else "",
    }


def destino_extra(d: dict) -> dict:
    """Calcula costos y estado de un lugar del buscador (no está en el globo)."""
    c = calcular(d, origen, dias, viajeros, tipo_aloj, precios_tp)
    f = {**d, "calc": c, "rank": None, "visitas": None}
    if turisticos:
        f["estado"] = "sin_datos"
    elif generales:
        f["estado"] = ESTADOS_GENERALES[sum(metrica(f) > x for x in cortes)][0] if cortes else "intermedio"
    else:
        f["estado"] = estado_presupuesto(c.total, presupuesto_usd)
    return f


with tab_lista:
    busqueda = st.text_input(
        "🔎 Buscar ciudad o pueblo", key="busqueda",
        placeholder="Ej.: Pucón, Cusco, Hallstatt, Chiloé…",
        help="Busca en los destinos del globo y en todas las ciudades y pueblos del mundo con "
             "más de 1.000 habitantes (base abierta GeoNames). Para los lugares que no están en "
             "el globo, los costos se estiman con el promedio de su país.")
    q = lugares.normalizar(busqueda)
    if len(q) >= 2:
        del_globo = [f for f in filas
                     if q in lugares.normalizar(f["ciudad"]) or q in lugares.normalizar(f["pais"])]
        extras = []
        if lugares.cantidad() == 0:
            with st.spinner("Descargando la lista mundial de ciudades y pueblos (solo la primera vez, "
                            "puede tardar unos 30 segundos)…"):
                lugares.cargar()
        if lugares.cantidad():
            ya = {(lugares.normalizar(f["ciudad"].split(" (")[0]), f["iso3"]) for f in DESTINOS}
            for fila in lugares.buscar(busqueda).itertuples(index=False):
                if (lugares.normalizar(fila.nombre), fila.iso3) in ya:
                    continue   # ya está en el globo
                d = lugares.como_destino(fila, DESTINOS)
                if ocultar_riesgo and d["riesgo"]:
                    continue
                f = destino_extra(d)
                if ocultar_fuera and f["estado"] == "fuera":
                    continue
                extras.append(f)
        else:
            st.warning("No se pudo descargar la lista mundial de ciudades (GeoNames); por ahora "
                       "solo se buscan los destinos del globo."
                       + (f" Detalle: {lugares.error_carga}" if lugares.error_carga else ""))
        resultado = del_globo + extras
        for f in extras:   # así también se pueden abrir en "Explorar destino" y "Alojamientos"
            por_id[f["id"]] = f
            opciones_ids.append(f["id"])
        st.caption(f"**{len(del_globo)}** destino{'s' if len(del_globo) != 1 else ''} del globo y "
                   f"**{len(extras)}** ciudad{'es' if len(extras) != 1 else ''} o pueblo"
                   f"{'s' if len(extras) != 1 else ''} más"
                   + (f" (se muestran los primeros {lugares.MAX_RESULTADOS}: escribe más letras para afinar)"
                      if len(extras) >= lugares.MAX_RESULTADOS - 5 else "")
                   + ". Los que no están en el globo también se pueden ver en «Explorar destino».")
    else:
        resultado = filas
        if lugares.cantidad():
            st.caption(f"¿No encuentras tu destino? Búscalo arriba entre "
                       f"{lugares.cantidad():,} ciudades y pueblos del mundo.".replace(",", "."))
        else:
            st.caption("¿No encuentras tu destino? Búscalo arriba: además de los destinos del globo, "
                       "el buscador incluye todas las ciudades y pueblos del mundo con más de 1.000 habitantes.")

    if not resultado:
        st.info("No hay destinos con esa búsqueda o con los filtros actuales.")
    else:
        tabla = pd.DataFrame([fila_tabla(f) for f in resultado])
        if generales or turisticos:
            tabla = tabla.drop(columns=["% del presupuesto"])
        if not popularidad.en_vivo:
            tabla = tabla.drop(columns=["Visitas Wikipedia (30 días)"])
        if precios_tp is None:
            tabla = tabla.drop(columns=["Precio del vuelo"])
        if not any(f.get("extra") for f in resultado):
            tabla = tabla.drop(columns=["En el globo", "Población"])
        st.dataframe(
            tabla, hide_index=True, width="stretch", height=420,
            column_config={
                "% del presupuesto": st.column_config.ProgressColumn(
                    format="%.0f%%", min_value=0, max_value=200),
                "Población": st.column_config.NumberColumn(format="localized"),
            },
        )
        st.caption(("Los vuelos marcados ✈ son precios reales de búsquedas recientes en Aviasales "
                    "(pueden cambiar); todo lo demás es estimado. " if n_reales else
                    "Todos los valores son estimados. ")
                   + "El total incluye vuelos ida y vuelta, alojamiento, alimentación, transporte "
                     "local y actividades para todo el grupo."
                   + (" En los lugares que no están en el globo, el costo de vida es el promedio de "
                      "su país (o de su región, si el país no tiene destinos en el globo)."
                      if any(f.get("extra") for f in resultado) else ""))

# ---- Detalle de un destino ----
with tab_explorar:
    if not opciones_ids:
        st.info("No hay destinos con los filtros actuales.")
    else:
        dest_id = st.selectbox("Destino", opciones_ids, format_func=etiqueta_dest, key="dest_explorar")
        f = por_id[dest_id]
        c = f["calc"]
        izq, der = st.columns([1.1, 1])

        with izq:
            wiki = _wiki(f["wiki"])
            if wiki and wiki.get("imagen"):
                st.image(wiki["imagen"], width="stretch")
            st.markdown(f"## {f['ciudad']}")
            if f.get("extra"):
                st.caption(f"Ciudad o pueblo de {f['pais']} · {f['poblacion']:,} habitantes".replace(",", ".")
                           + " (GeoNames). No está en el globo: el costo de vida es el promedio de "
                           + ("su país." if f["base_costos"] == "país" else "su región."))
            else:
                st.caption(f"Puesto **#{f['rank']}** entre los destinos más turísticos de {f['pais']}"
                           + (f" · {f['visitas']:,} visitas en Wikipedia (30 días)".replace(",", ".")
                              if f.get("visitas") else ""))
            if f.get("riesgo"):
                st.warning("Este país tiene advertencias de seguridad relevantes para viajeros "
                           "(dato referencial). Revisa las recomendaciones de viaje de la "
                           "cancillería de tu país antes de planificar.", icon="⚠️")
            st.markdown(f"<span class='etq' style='color:{colores[f['estado']]}'>"
                        f"{textos[f['estado']]}</span>", unsafe_allow_html=True)
            if wiki and wiki.get("extracto"):
                st.write(wiki["extracto"])
                if wiki.get("url"):
                    st.caption(f"Fuente: [Wikipedia]({wiki['url']})")
            else:
                motivo = wiki.get("error") if wiki else None
                st.caption("No se pudo cargar la información de Wikipedia"
                           + (f": {motivo}." if motivo else "."))
            if f["atractivos"]:
                st.markdown("**Atractivos y actividades**")
                st.markdown("\n".join(f"- {a}" for a in f["atractivos"]))

        with der:
            st.markdown("#### Costo total estimado del viaje")
            st.markdown(f"<div style='font-size:2.1rem;font-weight:700;color:{colores[f['estado']]}'>"
                        f"{fmt(c.total)}</div>", unsafe_allow_html=True)
            if presupuesto_usd:
                diferencia = presupuesto_usd - c.total
                st.caption(("Te sobran " if diferencia >= 0 else "Te faltan ") + fmt(abs(diferencia)))
            st.dataframe(pd.DataFrame({
                "Concepto": [f"Vuelos ida y vuelta ({viajeros} pers.)", f"Alojamiento ({noches} noches)",
                             "Alimentación", "Transporte local", "Actividades"],
                "Monto": [fmt(c.vuelos), fmt(c.alojamiento), fmt(c.comida),
                          fmt(c.transporte), fmt(c.actividades)],
                "Tipo": ["✈ Real (búsquedas recientes)" if c.vuelo_real else "Estimado"]
                        + ["Estimado"] * 4,
            }), hide_index=True, width="stretch")

            st.markdown("#### Costo de vida en destino")
            st.write(f"**{fmt(c.diario_pp)}** por persona por día, sin contar el vuelo "
                     f"(incluye {TIPOS_ALOJAMIENTO[tipo_aloj].lower()}).")

            st.markdown("#### Vuelo")
            if c.ruta.por_tierra:
                st.write("El destino está muy cerca de tu origen: se asume viaje por tierra (sin vuelo).")
            elif c.vuelo_real:
                r = c.vuelo_real
                st.write(f"✈ **Precio real de búsquedas recientes:** **{fmt(r.precio_pp)}** ida y vuelta "
                         f"por persona")
                st.write(f"**{r.aeropuerto_origen} → {r.aeropuerto_destino}** · {texto_vuelo_real(r)}")
                st.caption("Es el pasaje más barato que personas usuarias de Aviasales encontraron en "
                           "sus búsquedas de los últimos días"
                           + ("" if usar_fechas else " para un viaje de duración parecida")
                           + ". Puede haber cambiado o agotarse: confírmalo antes de comprar."
                           + (f" Consultado {precios_tp.consultado.astimezone().strftime('%d/%m/%Y %H:%M')}."
                              if precios_tp.consultado else ""))
                st.link_button("Ver este vuelo en Aviasales ↗", r.enlace(int(viajeros)), width="stretch")
            else:
                st.write(f"Estimado: **{fmt(c.vuelo_pp)}** ida y vuelta por persona · "
                         f"{c.distancia_km:,.0f} km volados".replace(",", "."))
                st.write(f"**Ruta:** {c.ruta.recorrido()} · {c.ruta.texto()}")
                if c.ruta.escalas:
                    st.caption("No hay vuelo directo estimado desde tu origen: el precio suma "
                               "cada tramo de la ruta más barata (máximo 4 escalas).")
                if precios_tp is not None:
                    st.caption("No hay precio real reciente para este destino"
                               + (f" ({precios_tp.periodo})" if precios_tp.periodo else "")
                               + ": se muestra el estimado.")
                    if usar_fechas and c.ruta.aeropuerto_final:
                        st.link_button("Buscar este vuelo en Aviasales ↗",
                                       travelpayouts.enlace_busqueda(origen, c.ruta.aeropuerto_final,
                                                                     llegada, salida, int(viajeros)),
                                       width="stretch")

            # Verificación en tiempo real (solo si hay credenciales reales)
            if not vuelos.duffel_configurado():
                if precios_tp is None:
                    st.caption("Para ver precios reales de vuelos, configura TRAVELPAYOUTS_TOKEN "
                               "en los Secrets de la app (ver README).")
            elif not usar_fechas:
                st.caption("Activa “Tengo fechas definidas” para verificar el precio real del vuelo.")
            elif not c.ruta.aeropuerto_final or c.ruta.por_tierra:
                st.caption("Este destino no tiene un aeropuerto propio identificado para verificar el vuelo.")
            elif c.ruta.aeropuerto_final == origen:
                st.caption("El destino está en tu ciudad de origen.")
            else:
                if st.button("Verificar precio real del vuelo (Duffel)", key=f"duffel_{dest_id}"):
                    with st.spinner("Consultando aerolíneas…"):
                        try:
                            oferta = vuelos.verificar_duffel(origen, c.ruta.aeropuerto_final, llegada, salida, int(viajeros))
                            if oferta is None:
                                st.info("Duffel no devolvió ofertas para esa ruta y fechas.")
                            else:
                                total_usd = tipos_cambio.a_usd(oferta.precio_total, oferta.moneda, tasas) \
                                    if oferta.moneda in tasas.por_usd else None
                                st.success(
                                    f"**Verificado:** {oferta.precio_total:,.2f} {oferta.moneda} total "
                                    f"({viajeros} pers.) · {oferta.aerolinea}"
                                    + (f" · ≈ {fmt(total_usd)}" if total_usd else ""))
                                st.caption(f"Consultado {oferta.consultado.astimezone().strftime('%d/%m/%Y %H:%M')}"
                                           + (" (desde caché)" if oferta.desde_cache else "")
                                           + f" · ruta {origen}–{c.ruta.aeropuerto_final}")
                                if oferta.modo_prueba:
                                    st.warning("Token de PRUEBA de Duffel: estas ofertas son de su "
                                               "entorno de pruebas, no tarifas reales.")
                        except vuelos.ErrorVuelos as e:
                            st.error(str(e))

# ---- Alojamientos ----
with tab_aloj:
    if not opciones_ids:
        st.info("No hay destinos con los filtros actuales.")
    else:
        proveedor = alojamientos.proveedor_activo()
        a1, a2, a3 = st.columns([1.6, 1, 1])
        dest_a = a1.selectbox("Destino", opciones_ids, format_func=etiqueta_dest,
                              index=opciones_ids.index(st.session_state.get("dest_explorar", opciones_ids[0]))
                              if st.session_state.get("dest_explorar") in opciones_ids else 0,
                              key="dest_aloj")
        tipo_filtro = a2.selectbox("Tipo", [None] + list(TIPOS_ALOJAMIENTO),
                                   format_func=lambda t: "Todos" if t is None else TIPOS_ALOJAMIENTO[t])
        tope = a3.number_input(f"Máx. por noche ({moneda})", min_value=0, value=0, step=paso,
                               help="0 = sin límite")

        lista = proveedor.buscar(por_id[dest_a], noches, int(viajeros), tipo_filtro, llegada, salida)
        if tope:
            lista = [x for x in lista
                     if tipos_cambio.convertir(x.precio_noche_usd, moneda, tasas) <= tope]

        if isinstance(proveedor, alojamientos.ProveedorDemo):
            st.markdown('<div class="aviso-demo">Estos alojamientos son <b>ejemplos ficticios</b> '
                        'generados a partir de precios promedio. El botón abre una búsqueda real '
                        'en Booking.com con tu destino, fechas y huéspedes.</div>', unsafe_allow_html=True)

        if not lista:
            st.info("Ninguna opción cumple el precio máximo.")
        else:
            columnas = st.columns(3)
            for i, a in enumerate(lista):
                with columnas[i % 3].container(border=True):
                    st.markdown(f"**{a.nombre}**")
                    st.caption(f"{TIPOS_ALOJAMIENTO[a.tipo]} · {a.zona}")
                    st.markdown(f"{fmt(a.precio_noche_usd)} / noche · **{fmt(a.precio_total_usd)}** total "
                                f"({noches} noches)")
                    st.caption(f"Calificación {a.calificacion}/10 · "
                               + ("Disponibilidad no verificada" if a.disponible is None
                                  else "Disponible" if a.disponible else "Sin disponibilidad"))
                    st.link_button("Buscar en Booking.com" if a.es_demo else "Ver / reservar",
                                   a.enlace, width="stretch")

            st.markdown("#### Comparar alternativas")
            nombres = [a.nombre for a in lista]
            elegidos = st.multiselect("Elige 2 o más", nombres, default=nombres[:3])
            if len(elegidos) >= 2:
                comp = [a for a in lista if a.nombre in elegidos]
                st.dataframe(pd.DataFrame({
                    "Alojamiento": [a.nombre for a in comp],
                    "Tipo": [TIPOS_ALOJAMIENTO[a.tipo] for a in comp],
                    "Zona": [a.zona for a in comp],
                    f"Por noche ({moneda})": [round(tipos_cambio.convertir(a.precio_noche_usd, moneda, tasas)) for a in comp],
                    f"Total ({moneda})": [round(tipos_cambio.convertir(a.precio_total_usd, moneda, tasas)) for a in comp],
                    "Calificación": [a.calificacion for a in comp],
                    "Origen del dato": ["Demostración" if a.es_demo else proveedor.nombre for a in comp],
                }), hide_index=True, width="stretch")

# ---- Transparencia de datos ----
with tab_fuentes:
    fuente_vuelos = (f"Travelpayouts (Aviasales): {n_reales} destinos con precio real; el resto, "
                     "fórmula por distancia" if n_reales else "Fórmula por distancia")
    if vuelos.duffel_configurado():
        fuente_vuelos += " + Duffel bajo demanda"
    estado_vuelos = ("✅ Real de búsquedas recientes (✈) + 🟡 estimado" if n_reales
                     else "✅ Verificación real disponible" if vuelos.duffel_configurado()
                     else "🟡 Estimado (demostración)")
    st.markdown(f"""
| Dato | Fuente actual | Estado |
|---|---|---|
| Tipo de cambio | {tasas.fuente} | {"⚠️ Respaldo fijo" if tasas.es_respaldo else "✅ Real, actualizado cada ~24 h"} |
| Vuelos | {fuente_vuelos} | {estado_vuelos} |
| Alojamientos | {proveedor.nombre if filas else "—"} | 🟡 Ejemplos ficticios + enlace a búsqueda real |
| Costo de vida (comida, transporte, actividades) | `datos/destinos.json` | 🟡 Estimado manual (demostración) |
| Fotos e información general | Wikipedia en español | ✅ Real |
| Ranking de destinos por país | {"Visitas a Wikipedia en los últimos 30 días" if popularidad.en_vivo else "Lista base compilada manualmente"} | {"✅ Real, actualizado cada 3 días" if popularidad.en_vivo else "🟡 Base (sin conexión)"} |
| Ciudades y pueblos del buscador | GeoNames (CC BY 4.0): ciudades y pueblos con más de 1.000 habitantes | ✅ Real (nombre, ubicación y población) · 🟡 costos estimados con el promedio del país |
| Llegadas de turistas por país | Cifras aproximadas 2023–2024 (ONU Turismo y fuentes nacionales) | 🟡 Referencial, fijo |
""")
    if popularidad.error and not popularidad.en_vivo:
        st.caption(f"Ranking en vivo no disponible: {popularidad.error}.")
    elif popularidad.actualizado:
        st.caption(f"Ranking turístico actualizado: {popularidad.actualizado.astimezone().strftime('%d/%m/%Y %H:%M')} "
                   f"· {popularidad.cobertura:.0%} de los destinos con datos de visitas.")
    if precios_tp is not None:
        if precios_tp.error:
            st.caption(f"Precios reales de vuelos no disponibles: {precios_tp.error}.")
        elif precios_tp.consultado:
            st.caption(f"Precios reales de vuelos ({precios_tp.periodo}): consultados "
                       f"{precios_tp.consultado.astimezone().strftime('%d/%m/%Y %H:%M')}"
                       + (" (desde caché)" if precios_tp.desde_cache else "")
                       + f" · {precios_tp.cantidad} ciudad{'es' if precios_tp.cantidad != 1 else ''} con precio desde {origen} · "
                         f"consultas a Travelpayouts hoy: {vuelos.cache.llamadas_hoy('travelpayouts')}"
                       + ("" if travelpayouts.marker() else
                          " · falta TRAVELPAYOUTS_MARKER: los enlaces no son de afiliado") + ".")
    st.caption(f"Consultas a Duffel hoy: {vuelos.cache.llamadas_hoy('duffel')}. "
               "Las respuestas de APIs se guardan en `datos/cache.db` con su fecha y hora.")
