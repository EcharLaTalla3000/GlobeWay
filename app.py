"""
GLOBEWAY — app principal (Streamlit)

¿Con cuánto dinero cuento, desde dónde quiero viajar y a qué lugares del mundo
puedo ir con ese presupuesto?

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import os
import random
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

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
  .solo-movil { display: none; }
  /* ---- Celulares (ojo: sin líneas en blanco dentro de este bloque, o Streamlit lo muestra como texto) ---- */
  @media (max-width: 700px) {
    .block-container { padding-top: .8rem; padding-left: .75rem; padding-right: .75rem; }
    .marca { font-size: 1.35rem; }
    .bajada { font-size: .88rem; margin-bottom: .6rem; }
    .aviso-demo { font-size: .78rem; padding: .45rem .7rem; }
    /* Indicadores en 2 columnas en vez de 4 filas */
    div[data-testid="stHorizontalBlock"]:has(.kpi) { flex-wrap: wrap !important; gap: .5rem !important; }
    div[data-testid="stHorizontalBlock"]:has(.kpi) > div[data-testid="stColumn"] {
      flex: 1 1 calc(50% - .5rem) !important; min-width: calc(50% - .5rem) !important; width: auto !important; }
    .kpi { padding: .55rem .7rem; }
    .kpi .n { font-size: 1.2rem; }
    .kpi .t { font-size: .72rem; }
    /* Pestañas: se deslizan de lado */
    div[data-testid="stTabs"] [role="tablist"] { overflow-x: auto; scrollbar-width: none; }
    div[data-testid="stTabs"] button p { font-size: .85rem; }
    .solo-movil { display: block; color: #94a3b8; font-size: .8rem; margin: -.3rem 0 .6rem; }
  }
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
# Enlace para compartir: la búsqueda se guarda en la dirección (URL) de la página.
# Al abrir un enlace compartido, se leen sus valores una sola vez por sesión.
# --------------------------------------------------------------------------
APP_URL = os.getenv("APP_URL", "https://globeway.streamlit.app").rstrip("/")


def _cargar_desde_url() -> None:
    ss, qp = st.session_state, st.query_params
    if ss.get("_url_cargada"):
        return
    ss["_url_cargada"] = True

    def entero(k, lo, hi):
        try:
            v = int(qp[k])
            return v if lo <= v <= hi else None
        except (KeyError, TypeError, ValueError):
            return None

    modo = qp.get("modo", "")
    ss["cfg_generales"], ss["cfg_turisticos"] = modo == "general", modo == "turismo"
    moneda = qp.get("moneda")
    if moneda in tipos_cambio.MONEDAS:
        ss["cfg_moneda"] = moneda
        if (p := entero("p", 0, 10**11)) is not None:
            ss[f"cfg_presupuesto_{moneda}"] = p
    if qp.get("o") in vuelos.ORIGENES:
        ss["cfg_origen"] = qp["o"]
    try:
        ida, vuelta = date.fromisoformat(qp["ida"]), date.fromisoformat(qp["vuelta"])
        if date.today() <= ida < vuelta:
            ss["cfg_fechas"], ss["cfg_rango"] = True, (ida, vuelta)
    except (KeyError, ValueError):
        pass
    if (d := entero("d", 2, 30)) is not None:
        ss["cfg_dias"] = d
    if (v := entero("v", 1, 10)) is not None:
        ss["cfg_viajeros"] = v
    if qp.get("aloj") in TIPOS_ALOJAMIENTO:
        ss["cfg_aloj"] = qp["aloj"]
    ss["favoritos"] = [x for x in qp.get("fav", "").split(",") if x][:20]
    if qp.get("dest"):
        ss["_dest_url"] = qp["dest"]


def _defecto(clave: str, valor) -> None:
    """Valor inicial de un control (si no viene del enlace ni de antes)."""
    if clave not in st.session_state:
        st.session_state[clave] = valor


_cargar_desde_url()

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
    _defecto("cfg_generales", False)
    _defecto("cfg_turisticos", False)
    generales = st.toggle(
        "Precios generales", key="cfg_generales",
        help="Colorea el mapa según lo caro o barato de cada destino comparado con el "
             "resto del mundo, sin necesidad de ingresar un presupuesto.")
    turisticos = st.toggle(
        "Más turísticos", key="cfg_turisticos",
        help="Muestra un mapa de calor de las zonas más visitadas del mundo. Con conexión, "
             "el ranking se actualiza con las visitas recientes a cada destino en Wikipedia.")
    if turisticos and generales:
        st.caption("El mapa muestra «Más turísticos»; «Precios generales» se aplica a las tablas.")

    st.markdown("### Tu viaje")
    _defecto("cfg_moneda", next(iter(tipos_cambio.MONEDAS)))
    moneda = st.selectbox("Moneda", list(tipos_cambio.MONEDAS), key="cfg_moneda",
                          format_func=lambda m: f"{m} · {tipos_cambio.MONEDAS[m]['nombre']}")
    paso = 50_000 if moneda == "CLP" else 50
    if generales or turisticos:
        presupuesto = 0
    else:
        por_defecto = {"CLP": 2_000_000, "USD": 2_000, "EUR": 1_900}.get(moneda, 2000)
        _defecto(f"cfg_presupuesto_{moneda}", por_defecto)
        presupuesto = st.number_input(f"Presupuesto total ({moneda})", min_value=0,
                                      step=paso, key=f"cfg_presupuesto_{moneda}")

    _defecto("cfg_origen", next(iter(vuelos.ORIGENES)))
    origen = st.selectbox("Desde dónde viajas", list(vuelos.ORIGENES), key="cfg_origen",
                          format_func=lambda c: vuelos.ORIGENES[c]["nombre"])

    _defecto("cfg_fechas", False)
    usar_fechas = st.toggle("Tengo fechas definidas", key="cfg_fechas")
    if usar_fechas:
        hoy = date.today()
        _defecto("cfg_rango", (hoy + timedelta(days=30), hoy + timedelta(days=37)))
        rango = st.date_input("Fechas (ida – vuelta)", key="cfg_rango",
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
        _defecto("cfg_dias", 8)
        dias = st.slider("Duración (días)", 2, 30, key="cfg_dias")

    _defecto("cfg_viajeros", 2)
    viajeros = st.number_input("Viajeros", 1, 10, key="cfg_viajeros")
    _defecto("cfg_aloj", list(TIPOS_ALOJAMIENTO)[1])
    tipo_aloj = st.selectbox("Alojamiento", list(TIPOS_ALOJAMIENTO), key="cfg_aloj",
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
    zona_compartir = st.container()   # se llena al final, con el enlace de esta búsqueda
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

# Ranking turístico: visitas en Wikipedia (en vivo) o ranking base (sin conexión).
# Wikipedia se consulta en segundo plano: la página no la espera. Cuando termina,
# este pequeño "fragmento" lo detecta y actualiza la página una vez.
popularidad = turismo.obtener_popularidad(DESTINOS)
RANKING = turismo.calcular_ranking(DESTINOS, popularidad)
if popularidad.actualizando:
    @st.fragment(run_every=5)
    def _esperar_ranking():
        if not turismo.actualizando():
            st.rerun()
    _esperar_ranking()

# La lista mundial de ciudades (buscador) se descarga en segundo plano, sin frenar la app
lugares.precargar()

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
    partes = [r.fechas_txt() + (" (fechas cercanas a las tuyas)" if getattr(r, "fechas_cercanas", False) else ""),
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
st.markdown('<div class="solo-movil">☰ Para cambiar presupuesto, origen o fechas, toca la '
            'flecha <b>»</b> arriba a la izquierda.</div>', unsafe_allow_html=True)
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
        ("En vivo" if popularidad.en_vivo else "Cargando…" if popularidad.actualizando else "Base",
         "ranking por visitas a Wikipedia (30 días)" if popularidad.en_vivo
         else "consultando Wikipedia; mientras, ranking base" if popularidad.actualizando
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

# ---- Botón "Sorpréndeme": elige al azar un destino que te alcanza ----
ir_a_pestana = None
enfoque = None
_, col_sorpresa = st.columns([4, 1])
if col_sorpresa.button("🎲 Sorpréndeme", width="stretch",
                       help="Elige al azar un destino que te alcanza (o uno de los más "
                            "turísticos, en ese modo) y te lo muestra en el globo."):
    if turisticos:
        candidatos = [f for f in filas if (f.get("rank") or 99) <= 3]
    else:
        candidatos = ([f for f in filas if f["estado"] in ("economico", "intermedio")]
                      or [f for f in filas if f["estado"] == "costoso"])
    candidatos = [f for f in candidatos if not f.get("riesgo")] or candidatos
    if candidatos:
        elegido = random.choice(candidatos)
        st.session_state["dest_explorar"] = elegido["id"]
        st.session_state["pais_globo"] = elegido["iso3"]
        enfoque = {"id": elegido["id"], "t": time.time()}
        ir_a_pestana = "Explorar destino"
        st.toast(f"🎲 ¡Te tocó **{elegido['ciudad']}** ({elegido['pais']})! "
                 "Mira el detalle en «Explorar destino».")
    else:
        st.toast("No hay destinos que te alcancen con este presupuesto. Prueba subiéndolo "
                 "o cambiando la duración del viaje.")

clic = mostrar_globo(datos_globo, alto=640, enfoque=enfoque)

# ---- El clic en el globo actualiza las pestañas de abajo ----
# El globo devuelve el último clic con su hora ("t"); se procesa una sola vez.
if clic and clic.get("t") != st.session_state.get("_ultimo_clic"):
    st.session_state["_ultimo_clic"] = clic.get("t")
    ids_globo = {f["id"]: f for f in filas}
    if clic.get("tipo") == "destino" and clic.get("id") in ids_globo:
        f_clic = ids_globo[clic["id"]]
        st.session_state["dest_explorar"] = clic["id"]
        st.session_state["pais_globo"] = f_clic["iso3"]
        ir_a_pestana = "Explorar destino"
        st.toast(f"📍 {f_clic['ciudad']}: mira el detalle en «Explorar destino», bajo el globo.")
    elif clic.get("tipo") == "pais" and clic.get("iso3"):
        st.session_state["pais_globo"] = clic["iso3"]
        ir_a_pestana = "Destinos"
    elif clic.get("tipo") in ("cerrar", "pais"):
        st.session_state.pop("pais_globo", None)
pais_globo = st.session_state.get("pais_globo")
if pais_globo and not any(f["iso3"] == pais_globo for f in filas):
    pais_globo = None


# --------------------------------------------------------------------------
# Pestañas inferiores
# --------------------------------------------------------------------------


def grafico(chart) -> None:
    """Muestra un gráfico de Altair a todo el ancho (compatible con varias versiones)."""
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def alternar_favorito(dest: str) -> None:
    favs = st.session_state.setdefault("favoritos", [])
    if dest in favs:
        favs.remove(dest)
    else:
        favs.append(dest)


tab_lista, tab_explorar, tab_comparar, tab_aloj, tab_fuentes = st.tabs(
    ["Destinos", "Explorar destino", "Comparar", "Alojamientos", "Datos y fuentes"])

opciones_ids = [f["id"] for f in filas]
por_id = {f["id"]: f for f in filas}

# Destino que venía en un enlace compartido
if st.session_state.get("_dest_url") in por_id:
    st.session_state["dest_explorar"] = st.session_state.pop("_dest_url")
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
                 + (" (fechas cercanas)" if getattr(r, "fechas_cercanas", False) else "")) if r
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
        resultado = [f for f in filas if f["iso3"] == pais_globo] if pais_globo else filas
        if pais_globo:
            nombre_sel = resultado[0]["pais"]
            c1, c2 = st.columns([3, 1])
            c1.caption(f"Mostrando los **{len(resultado)}** destinos de **{nombre_sel}** "
                       "(elegido en el globo).")
            c2.button("Ver todos los países", key="quitar_pais", width="stretch",
                      on_click=lambda: st.session_state.pop("pais_globo", None))
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
            if not f.get("extra"):
                es_fav = dest_id in st.session_state.get("favoritos", [])
                st.button("★ Quitar de favoritos" if es_fav else "☆ Guardar en favoritos",
                          key=f"fav_{dest_id}", on_click=alternar_favorito, args=(dest_id,),
                          help="Tus favoritos quedan en el enlace de la página: guárdalo o "
                               "compártelo para no perderlos. También puedes compararlos "
                               "en la pestaña «Comparar».")
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

        # ---- ¿Cuándo es más barato ir? ----
        if not c.ruta.por_tierra:
            st.markdown("#### 📅 ¿Cuándo es más barato ir?")
            codigo_dest = ((c.vuelo_real.aeropuerto_destino if c.vuelo_real else None)
                           or f.get("iata") or c.ruta.aeropuerto_final)
            if not travelpayouts.configurado():
                st.caption("Necesita TRAVELPAYOUTS_TOKEN en los Secrets de la app (ver README).")
            elif not codigo_dest or codigo_dest.startswith("@"):
                st.caption("Este destino no tiene un aeropuerto identificado para buscar precios por mes.")
            else:
                clave_meses = f"{origen}:{codigo_dest}"
                if st.session_state.get("meses_ver") != clave_meses:
                    st.caption("Mira el pasaje más barato de cada uno de los próximos 12 meses, "
                               "según búsquedas reales recientes en Aviasales.")
                    if st.button("Ver precios por mes", key=f"meses_{dest_id}"):
                        st.session_state["meses_ver"] = clave_meses
                if st.session_state.get("meses_ver") == clave_meses:
                    with st.spinner("Buscando precios por mes…"):
                        lista_meses, error_meses = travelpayouts.precios_por_mes(origen, codigo_dest, noches)
                    if not lista_meses:
                        st.info("No hay precios recientes por mes para esta ruta"
                                + (f" ({error_meses})." if error_meses else ".")
                                + " Prueba con otro destino cercano o más tarde.")
                    else:
                        parecidos = [m for m in lista_meses if not m.otra_duracion] or lista_meses
                        barato = min(parecidos, key=lambda m: m.precio.precio_pp)
                        st.success(f"El mes más barato es **{barato.mes_txt}**: "
                                   f"**{fmt(barato.precio.precio_pp)}** por persona, ida y vuelta "
                                   f"({barato.precio.fechas_txt()}, {barato.noches} noches).")
                        filas_mes = [{
                            "Mes": m.mes_txt, "orden": m.mes,
                            "Precio": round(tipos_cambio.convertir(m.precio.precio_pp, moneda, tasas)),
                            "Fechas": m.precio.fechas_txt(), "Noches": m.noches,
                            "Escalas": m.precio.escalas_txt(),
                            "Duración": "Otra duración" if m.otra_duracion else "Parecida a la tuya",
                            "Destacado": "Más barato" if m is barato else "",
                            "Ver": m.precio.enlace(int(viajeros)),
                        } for m in lista_meses]
                        tabla_mes = pd.DataFrame(filas_mes)
                        try:
                            import altair as alt
                            base = alt.Chart(tabla_mes).encode(
                                x=alt.X("Mes:N", sort=[m.mes_txt for m in lista_meses], title=None,
                                        axis=alt.Axis(labelAngle=-40)),
                                y=alt.Y("Precio:Q", title=f"Ida y vuelta por persona ({moneda})",
                                        axis=alt.Axis(format="~s", gridOpacity=0.15)),
                                tooltip=["Mes", alt.Tooltip("Precio:Q", format=",.0f"), "Fechas",
                                         "Noches", "Escalas", "Duración"])
                            barras = base.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                                                   stroke="#05070d", strokeWidth=2).encode(
                                color=alt.condition(alt.datum.Destacado == "Más barato",
                                                    alt.value("#F5A524"), alt.value("#3987e5")),
                                opacity=alt.condition(alt.datum["Duración"] == "Otra duración",
                                                      alt.value(0.45), alt.value(1.0)))
                            etiqueta = base.transform_filter(alt.datum.Destacado == "Más barato") \
                                .mark_text(dy=-8, color="#e5e9f0", fontSize=12).encode(text="Destacado:N")
                            grafico((barras + etiqueta).properties(height=260))
                        except Exception:
                            pass   # si el gráfico falla, igual se muestra la tabla
                        st.dataframe(
                            tabla_mes.drop(columns=["orden", "Destacado"]), hide_index=True, width="stretch",
                            column_config={
                                "Precio": st.column_config.NumberColumn(f"Precio p/p ({moneda})",
                                                                        format="localized"),
                                "Ver": st.column_config.LinkColumn("Aviasales", display_text="Ver ↗"),
                            })
                        st.caption(f"Precios reales de búsquedas recientes, por persona, ida y vuelta. "
                                   f"Se prefieren viajes de duración parecida a la tuya (±{travelpayouts.tolerancia(noches)} "
                                   "noches); las barras más claras son meses donde solo hubo viajes de otra "
                                   "duración. Los meses sin búsquedas recientes no aparecen.")

# ---- Comparar destinos ----
CONCEPTOS = ["Vuelos", "Alojamiento", "Alimentación", "Transporte local", "Actividades"]
PALETA_CONCEPTOS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]   # validada para fondo oscuro

with tab_comparar:
    favs = [i for i in st.session_state.get("favoritos", []) if i in por_id]
    if favs:
        cf1, cf2 = st.columns([3, 1])
        cf1.caption("⭐ Tus favoritos: " + ", ".join(por_id[i]["ciudad"] for i in favs))
        cf2.button("Comparar mis favoritos", width="stretch", key="cmp_favs",
                   on_click=lambda: st.session_state.update(cmp_sel=favs[:3]))
    else:
        st.caption("Consejo: guarda destinos con ☆ en «Explorar destino» y aparecerán aquí.")
    if "cmp_sel" not in st.session_state:
        actual = st.session_state.get("dest_explorar")
        st.session_state["cmp_sel"] = favs[:3] or ([actual] if actual in por_id else [])
    st.session_state["cmp_sel"] = [i for i in st.session_state["cmp_sel"] if i in por_id][:3]
    sel_cmp = st.multiselect("Elige 2 o 3 destinos para comparar", opciones_ids, key="cmp_sel",
                             max_selections=3, format_func=etiqueta_dest,
                             placeholder="Escribe para buscar un destino…")
    if len(sel_cmp) < 2:
        st.info("Elige al menos 2 destinos.")
    else:
        elegidos = [por_id[i] for i in sel_cmp]
        mas_barato = min(elegidos, key=lambda x: x["calc"].total)
        mas_caro = max(elegidos, key=lambda x: x["calc"].total)
        if mas_barato is not mas_caro:
            st.success(f"💡 **{mas_barato['ciudad']}** es el más barato: ahorras "
                       f"**{fmt(mas_caro['calc'].total - mas_barato['calc'].total)}** frente a "
                       f"{mas_caro['ciudad']}.")

        def fila_cmp(x):
            c = x["calc"]
            return {
                "Total del viaje": fmt(c.total),
                "% del presupuesto": f"{c.total / presupuesto_usd * 100:.0f} %" if presupuesto_usd else "—",
                "Estado": textos[x["estado"]],
                "Vuelo por persona": fmt(c.vuelo_pp) + (" ✈ real" if c.vuelo_real else " (estimado)"),
                f"Vuelos ({viajeros} pers.)": fmt(c.vuelos),
                f"Alojamiento ({noches} noches)": fmt(c.alojamiento),
                "Alimentación": fmt(c.comida),
                "Transporte local": fmt(c.transporte),
                "Actividades": fmt(c.actividades),
                "Costo de vida por persona al día": fmt(c.diario_pp),
                "Escalas": str(c.vuelo_real.escalas_ida if c.vuelo_real else c.ruta.escalas),
                "Distancia volada": f"{c.distancia_km:,.0f} km".replace(",", "."),
                "Ranking en su país": f"#{x['rank']}" if x.get("rank") else "—",
                "Advertencias de seguridad": "⚠️ Sí" if x.get("riesgo") else "No",
            }

        tabla_cmp = pd.DataFrame({f"{x['ciudad']} ({x['pais']})": fila_cmp(x) for x in elegidos})
        st.dataframe(tabla_cmp, width="stretch")

        try:
            import altair as alt
            datos_cmp = pd.DataFrame([
                {"Destino": x["ciudad"], "Concepto": k, "orden": i,
                 "Monto": round(tipos_cambio.convertir(v, moneda, tasas))}
                for x in elegidos
                for i, (k, v) in enumerate(zip(CONCEPTOS, (x["calc"].vuelos, x["calc"].alojamiento,
                                                            x["calc"].comida, x["calc"].transporte,
                                                            x["calc"].actividades)))])
            chart_cmp = alt.Chart(datos_cmp).mark_bar(stroke="#05070d", strokeWidth=2).encode(
                y=alt.Y("Destino:N", sort=[x["ciudad"] for x in elegidos], title=None),
                x=alt.X("Monto:Q", stack="zero", title=f"Costo del viaje para {viajeros} pers. ({moneda})",
                        axis=alt.Axis(format="~s", gridOpacity=0.15)),
                color=alt.Color("Concepto:N", scale=alt.Scale(domain=CONCEPTOS, range=PALETA_CONCEPTOS),
                                legend=alt.Legend(orient="top", title=None)),
                order=alt.Order("orden:Q"),
                tooltip=["Destino", "Concepto", alt.Tooltip("Monto:Q", format=",.0f")],
            ).properties(height=70 * len(elegidos) + 50)
            grafico(chart_cmp)
        except Exception:
            pass   # si el gráfico falla, igual queda la tabla
        st.caption("Vuelos marcados ✈: precio real de búsquedas recientes; el resto de los montos son "
                   "estimados de demostración.")

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

# ---- Abrir la pestaña que corresponde al clic en el globo ----
# Streamlit no permite cambiar de pestaña desde Python; un script mínimo hace clic
# en la pestaña. Lleva la hora del clic para que se ejecute una vez por clic.
if ir_a_pestana:
    components.html(f"""<script>
(function () {{
  let intentos = 0;
  (function abrir() {{
    try {{
      const pestanas = [...window.parent.document.querySelectorAll('button[role="tab"]')];
      const p = pestanas.find(b => b.innerText.trim() === {ir_a_pestana!r});
      if (p) {{ if (p.getAttribute('aria-selected') !== 'true') p.click(); return; }}
    }} catch (e) {{ return; }}
    if (intentos++ < 20) setTimeout(abrir, 150);
  }})();
}})();
/* {st.session_state.get("_ultimo_clic")} */
</script>""", height=0)


# ---- Enlace para compartir (se arma al final, con todo lo elegido) ----
params_url = {"moneda": moneda, "o": origen, "v": str(int(viajeros)), "aloj": tipo_aloj}
if generales:
    params_url["modo"] = "general"
elif turisticos:
    params_url["modo"] = "turismo"
else:
    params_url["p"] = str(int(presupuesto))
if usar_fechas:
    params_url["ida"], params_url["vuelta"] = llegada.isoformat(), salida.isoformat()
else:
    params_url["d"] = str(int(dias))
favs_url = [i for i in st.session_state.get("favoritos", []) if not i.startswith("gn")]
if favs_url:
    params_url["fav"] = ",".join(favs_url)
dest_url = st.session_state.get("dest_explorar")
if dest_url and not str(dest_url).startswith("gn"):
    params_url["dest"] = dest_url
if dict(st.query_params) != params_url:
    st.query_params.from_dict(params_url)   # la dirección de la página siempre refleja la búsqueda
enlace_compartir = f"{APP_URL}/?{urlencode(params_url)}"
with zona_compartir:
    with st.expander("🔗 Compartir esta búsqueda"
                     + (f" · ⭐ {len(favs_url)}" if favs_url else "")):
        st.code(enlace_compartir, language=None, wrap_lines=True)
        st.caption("Copia el enlace con el botón de la esquina. Quien lo abra verá tu misma "
                   "búsqueda, tus favoritos y el destino que estás mirando. Guárdalo también "
                   "para no perder tus favoritos.")
