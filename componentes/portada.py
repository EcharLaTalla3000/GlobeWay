"""
Pantalla de inicio de GlobeWay.

Animación (solo CSS, dentro de un marco propio para que ningún navegador la altere):
  1. El logo (G + W) aparece grande al centro y se "dibuja".
  2. Se achica y se corre a la izquierda mientras de él sale el nombre
     "GlobeWay" y luego el lema.
  3. Un segundo después aparece el botón "Iniciar".
Al apretar "Iniciar" se guarda en la sesión y la app se carga normalmente.
"""
from __future__ import annotations

import streamlit as st

AZUL = "#0b1e3f"
AMBAR = "#f5a524"
BLANCO = "#f8fafc"

# Logo B: una G abierta que envuelve una W (ruta con escalas) y un punto de destino.
LOGO_SVG = f"""
<svg viewBox="0 0 120 120" class="gw-logo" role="img" aria-label="Logo de GlobeWay">
  <path class="gw-g" pathLength="100" d="M82 21.9 A44 44 0 1 0 104 60 H90"
        fill="none" stroke="{BLANCO}" stroke-width="11" stroke-linejoin="miter"/>
  <polyline class="gw-w" pathLength="100" points="32,46 44,80 60,56 76,80 88,46"
        fill="none" stroke="{AMBAR}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
  <circle class="gw-dot" cx="95" cy="31" r="6" fill="{AMBAR}"/>
</svg>
"""


def logo_mini(alto: int = 30) -> str:
    """Logo pequeño (sin animación) para el encabezado de la app."""
    return (f'<svg viewBox="0 0 120 120" width="{alto}" height="{alto}" aria-hidden="true" '
            f'style="vertical-align:-0.22em;margin-right:.45rem">'
            f'<path d="M82 21.9 A44 44 0 1 0 104 60 H90" fill="none" stroke="{BLANCO}" stroke-width="12"/>'
            f'<polyline points="32,46 44,80 60,56 76,80 88,46" fill="none" stroke="{AMBAR}" '
            f'stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="95" cy="31" r="7" fill="{AMBAR}"/></svg>')


# ---- Animación: va en un marco propio (iframe), así se ve igual en todos los navegadores ----
_ANIMACION = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;700&display=swap" rel="stylesheet">
<style>
html, body {{ margin: 0; height: 100%; background: {AZUL}; overflow: hidden; }}
.gw-portada {{ height: 100%; display: flex; align-items: center; justify-content: center;
  font-family: 'Sora', Inter, system-ui, sans-serif; }}
.gw-fila {{ display: flex; align-items: center; }}

/* 1) Logo: aparece grande, se dibuja y luego se achica */
.gw-logo {{ width: clamp(110px, 16vw, 190px); height: auto; flex: none;
  transform: scale(1.55); animation: gw-achicar 0.9s cubic-bezier(.65,0,.35,1) 1.5s forwards; }}
.gw-g, .gw-w {{ stroke-dasharray: 100; stroke-dashoffset: 100; }}
.gw-g {{ animation: gw-trazo 0.9s ease-out 0.15s forwards; }}
.gw-w {{ animation: gw-trazo 0.7s ease-out 0.75s forwards; }}
.gw-dot {{ opacity: 0; transform-origin: 95px 31px; transform: scale(0);
  animation: gw-punto 0.45s cubic-bezier(.34,1.56,.64,1) 1.25s forwards; }}

/* 2) El nombre "sale" del logo: el bloque de texto se abre de 0 a su ancho */
.gw-texto {{ max-width: 0; overflow: hidden; white-space: nowrap;
  animation: gw-abrir 1.0s cubic-bezier(.65,0,.35,1) 1.65s forwards; }}
.gw-texto-int {{ padding-left: clamp(18px, 2.6vw, 36px); opacity: 0; transform: translateX(-28px);
  animation: gw-salir 0.8s ease-out 1.8s forwards; }}
.gw-nombre {{ font-size: clamp(40px, 6.4vw, 92px); font-weight: 700; letter-spacing: -0.03em;
  line-height: 1.05; color: {BLANCO}; }}
.gw-nombre span {{ color: {AMBAR}; }}
.gw-lema {{ margin-top: 12px; font-size: clamp(14px, 1.5vw, 20px); color: #b6c2d6; opacity: 0;
  animation: gw-aparecer 0.6s ease-out 2.5s forwards; }}

@keyframes gw-trazo {{ to {{ stroke-dashoffset: 0; }} }}
@keyframes gw-punto {{ to {{ opacity: 1; transform: scale(1); }} }}
@keyframes gw-achicar {{ to {{ transform: scale(1); }} }}
@keyframes gw-abrir {{ to {{ max-width: 900px; }} }}
@keyframes gw-salir {{ to {{ opacity: 1; transform: translateX(0); }} }}
@keyframes gw-aparecer {{ to {{ opacity: 1; }} }}
@media (prefers-reduced-motion: reduce) {{
  * {{ animation-duration: 0.01s !important; animation-delay: 0s !important; }}
}}
</style></head>
<body>
<div class="gw-portada">
  <div class="gw-fila">
    {LOGO_SVG}
    <div class="gw-texto"><div class="gw-texto-int">
      <div class="gw-nombre">Globe<span>Way</span></div>
      <div class="gw-lema">Tu próximo destino, a tu medida</div>
    </div></div>
  </div>
</div>
</body></html>
"""

# ---- Estilos de la página de Streamlit mientras se muestra la portada ----
_CSS_PAGINA = f"""<style>
.stApp {{ background: {AZUL} !important; }}
section[data-testid="stSidebar"], div[data-testid="stSidebarCollapsedControl"],
button[data-testid="stExpandSidebarButton"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: transparent !important; }}
.block-container {{ padding-top: 8vh !important; }}
iframe {{ border: 0; }}

/* Botón "Iniciar": aparece 1 segundo después de terminar la animación */
.st-key-iniciar {{ display: flex !important; justify-content: center; opacity: 0; visibility: hidden;
  animation: gw-boton 0.6s ease-out 3.6s forwards; }}
.st-key-iniciar button {{ background: {AMBAR} !important; color: {AZUL} !important; border: 0 !important;
  border-radius: 999px !important; padding: 0.7rem 2.8rem !important; min-height: 48px;
  box-shadow: 0 10px 30px rgba(245,165,36,.25); transition: transform .15s, box-shadow .15s; }}
.st-key-iniciar button p {{ font-weight: 700 !important; font-size: 1.05rem !important; letter-spacing: .02em; }}
.st-key-iniciar button:hover {{ transform: translateY(-2px); box-shadow: 0 14px 34px rgba(245,165,36,.35); }}
@keyframes gw-boton {{ from {{ opacity: 0; visibility: visible; transform: translateY(8px); }}
                       to   {{ opacity: 1; visibility: visible; transform: translateY(0); }} }}
@media (prefers-reduced-motion: reduce) {{
  .st-key-iniciar {{ animation-duration: 0.01s !important; animation-delay: 0s !important; }}
}}
</style>"""


def mostrar_portada() -> None:
    """Muestra la portada animada y detiene la app hasta que se apriete "Iniciar"."""
    import streamlit.components.v1 as components
    st.markdown(_CSS_PAGINA, unsafe_allow_html=True)
    components.html(_ANIMACION, height=380)
    if st.button("Iniciar", key="iniciar"):
        st.session_state["iniciado"] = True
        st.rerun()
    st.stop()
