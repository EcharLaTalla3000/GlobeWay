# GlobeWay

Globo terráqueo 3D interactivo para descubrir a qué destinos del mundo puedes viajar según tu presupuesto, moneda, origen, duración, viajeros y tipo de alojamiento.

## Cómo ejecutarlo

Necesitas Python 3.10 o superior y conexión a internet (el globo carga sus texturas y mapas desde CDN).

```bash
cd globeway
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Se abre solo en el navegador, en `http://localhost:8501`.

## Qué hace

- **Globo 3D** (Globe.gl / WebGL): gira solo hasta que lo tocas; se puede arrastrar, acercar y hacer clic.
  - Clic en un **país**: abre una ficha con sus destinos y la pestaña *Destinos* muestra solo ese país.
  - Clic en un **punto**: desglose del viaje, un arco animado desde tu origen, y las pestañas *Explorar destino* y *Alojamientos* pasan a ese destino.
- **Colores**:
  - Modo *presupuesto* (por defecto): verde (≤60 %), amarillo (60–85 %), naranjo (85–100 %), violeta (hasta +15 %, ligeramente sobre) y rojo (fuera de presupuesto). Los destinos accesibles tienen un anillo pulsante.
  - Interruptor **Precios generales**: oculta el presupuesto y colorea cada destino según lo caro que es comparado con el resto del mundo (cuartiles), ya sea por costo total del viaje o por costo de vida en destino. La leyenda muestra los rangos de precio.
- Interruptor **Más turísticos**: mapa de calor 3D (columnas hexagonales) con las zonas más visitadas del mundo. La altura y el color de cada columna dependen de los turistas estimados en la zona: llegadas internacionales del país (cifra aproximada) × participación de cada destino.
- **Pantalla completa al tocar un destino** (computador): el globo ocupa toda la pantalla; al cerrar la ficha (× o Esc) vuelve a la vista normal. La ficha trae **✈ Ver vuelos disponibles** (abre Aviasales para comprar) y **🎟 Ver actividades**.
- **Lupas + / −** a la derecha del globo para acercar y alejar (solo computador).
- **☀️ Modo claro / 🌙 Modo oscuro**: botón arriba a la derecha; se recuerda en el navegador.
- **Actividades**: pestaña con lugares para visitar y cosas para hacer del destino (Wikivoyage) y búsqueda de tours en GetYourGuide.
- **Hoteles reales** (con `LITEAPI_KEY`): en *Alojamientos*, hasta 10 hoteles por cada nivel de estrellas con su precio para tus fechas.
- **Destinos sin aeropuerto**: se usa el precio real del aeropuerto más cercano (hasta 300 km) y la tabla muestra a qué distancia queda.
- **Celular**: el globo ocupa toda la pantalla; arriba hay una barra «Buscar destinos» que se expande y muestra las pestañas; «Calor vivo» siempre activo; el panel lateral parte cerrado.
- **🎲 Sorpréndeme** (en el panel lateral): elige al azar un destino que te alcanza (≤85 % del presupuesto, sin advertencias de seguridad), vuela hasta él en el globo y abre su detalle.
- **Comparar**: pestaña para poner 2 o 3 destinos lado a lado (tabla y gráfico de barras con vuelos, alojamiento, comida, transporte y actividades).
- **Favoritos y enlace para compartir**: ☆ en *Explorar destino* guarda favoritos. La búsqueda completa (moneda, presupuesto, origen, fechas o duración, viajeros, alojamiento, favoritos y destino) queda en la dirección de la página; el panel lateral muestra el enlace listo para copiar.
- **📅 ¿Cuándo es más barato ir?**: en *Explorar destino*, el pasaje real más barato de cada uno de los próximos 12 meses (Travelpayouts), con gráfico y enlaces a Aviasales.
- **Ranking por país**: al hacer clic en un país se ve su ranking de destinos más turísticos. Sin conexión se usa el ranking base; con conexión se actualiza con las visitas de los últimos 30 días a cada destino en Wikipedia (caché de 3 días).
- **1.512 destinos en 176 países**: hasta 10 por país y 20 en los cinco más grandes (Rusia, Canadá, EE. UU., China y Brasil). Los países con advertencias de seguridad se marcan con ⚠ y se pueden ocultar.
- **Vuelos con escalas**: si no hay vuelo directo estimado, se calcula la ruta más barata a través de una red de 37 hubs (máximo 4 escalas), sumando cada tramo. Los destinos sin aeropuerto propio (por ejemplo, Frutillar) usan el aeropuerto más cercano del país más un traslado terrestre. La ruta se dibuja en el globo con un arco por tramo.
- **Presupuesto** en CLP, USD o EUR, con tipo de cambio real (open.er-api.com).
- **Pestañas** bajo el globo:
  - *Destinos*: ranking.
  - *Explorar destino*: foto e información de Wikipedia, desglose y verificación de vuelo.
  - *Alojamientos*: opciones con comparador.
  - *Datos y fuentes*: qué es real y qué es estimado.

## Qué es real y qué es demostración

| Dato | Estado |
|---|---|
| Tipo de cambio | Real (si la API no responde, usa tasas de respaldo y lo avisa) |
| Fotos e información general | Real (Wikipedia en español) |
| Ranking de destinos por país | Real con conexión (visitas a Wikipedia, 30 días); sin conexión, lista base compilada manualmente |
| Llegadas de turistas por país | Cifras aproximadas 2023–2024 (referencia para el mapa de calor) |
| Vuelos | Con `TRAVELPAYOUTS_TOKEN`: **precio real de búsquedas recientes** en Aviasales (marcado ✈) para los destinos que tengan dato; el resto, **estimado** por distancia y ruta con escalas (`servicios/rutas.py`). Con Duffel se puede verificar un vuelo puntual |
| Costo de vida | **Estimado manual** en `datos/destinos.json` |
| Ciudades y pueblos del buscador | Nombre, ubicación y población **reales** (GeoNames, CC BY 4.0, más de 1.000 habitantes); costo de vida **estimado** con la mediana de su país o región |
| Alojamientos | **Ejemplos ficticios**, marcados como tales. El botón abre una búsqueda real en Booking.com |

## Publicar en Streamlit Community Cloud (URL fija y gratis)

1. Crea una cuenta en https://github.com y un repositorio nuevo (por ejemplo `globeway`).
2. Sube **el contenido** de esta carpeta (no la carpeta misma): `app.py` debe quedar en la raíz del repositorio.
   Revisa que se hayan subido `.gitignore` y `.streamlit/config.toml`.
3. Entra a https://share.streamlit.io con tu cuenta de GitHub → **Create app** → elige el repositorio,
   la rama `main` y el archivo `app.py`. En *Advanced settings* elige Python 3.12.
4. Si tienes tokens, pégalos en *Advanced settings → Secrets* (formato en `.streamlit/secrets.toml.example`).
5. **Deploy**. La URL queda como `https://<nombre>.streamlit.app`.

Las claves se leen con `servicios/secretos.py`, que busca en este orden: variables de entorno
(Colab), archivo `.env` (local) y Secrets de Streamlit Cloud. El `.gitignore` evita subir
`.env`, `secrets.toml` y la caché `datos/cache.db`.

> En Streamlit Cloud la app "se duerme" tras varios días sin visitas y la caché se borra al
> reiniciarse; solo significa que la primera carga vuelve a descargar datos.

## Configurar claves API (opcional)

1. Copia `.env.example` como `.env` (uso local), o usa los Secretos de Colab (🔑) o de Streamlit Cloud.
2. **Duffel (vuelos):**
   - Crea una cuenta en duffel.com y pega tu token en `DUFFEL_ACCESS_TOKEN`.
   - Con fechas activadas, en *Explorar destino* aparece el botón **Verificar precio real del vuelo**.
   - Las respuestas quedan en caché 6 horas (`datos/cache.db`), y hay un límite diario configurable en `DUFFEL_MAX_DIARIO`.
   - Un token de prueba (`duffel_test_…`) devuelve ofertas de prueba; la app lo advierte.
3. **Travelpayouts (precios reales de vuelos, datos de Aviasales):**
   - Regístrate en https://www.travelpayouts.com indicando la URL de la app (`https://globeway.streamlit.app`) y únete al programa **Aviasales**.
   - Copia tu **API token** (Perfil → *API token*) en `TRAVELPAYOUTS_TOKEN` y tu **ID de socio** (marker) en `TRAVELPAYOUTS_MARKER`.
   - Para cubrir la mayor cantidad de destinos, combina varias consultas por origen y fechas (unas 4 a 8: `prices_for_dates` por mes y `prices/latest`), las guarda 6 horas en caché y respeta `TRAVELPAYOUTS_MAX_DIARIO` (500 por defecto).
   - Con fechas: prefiere exactamente esas fechas y, si no hay, fechas cercanas (±7 días al salir), marcadas como tales. Sin fechas: salidas en los próximos ~2 meses. En ambos casos solo acepta viajes de duración parecida (±3 noches, o ±50 % en viajes largos).
   - Los destinos con dato muestran **✈ precio real de búsquedas recientes** y un botón a Aviasales con tu marker (enlace de afiliado). Los demás siguen estimados.
4. **LiteAPI (hoteles reales con precio):**
   - Crea una cuenta gratis en https://dashboard.liteapi.travel y copia tu clave en `LITEAPI_KEY`.
   - La clave de prueba (`sand_...`) se entrega al tiro, pero sus **precios son de prueba** (la app lo avisa). Para precios reales hay que activar la clave de producción (`prod_...`) en el panel de LiteAPI; según su documentación, para eso pide registrar una tarjeta, aunque las búsquedas son gratis.
   - (Opcional) `LITEAPI_WHITELABEL_URL`: tu sitio de reservas de LiteAPI, para que «Reservar» vaya ahí y ganes comisión.
5. **Booking.com:** la Demand API exige ser afiliado aprobado. El punto de conexión está preparado en `servicios/alojamientos.py` (`ProveedorBooking`), pero no está implementado, para no simular una API sin credenciales.

Nunca subas `.env` a un repositorio.

## Estructura

```
globeway/
├── app.py                    # Interfaz Streamlit (panel lateral, indicadores, pestañas)
├── componentes/
│   ├── globo_web/index.html  # Globo 3D (Globe.gl): países, puntos, arcos, ficha lateral
│   └── globo.py              # Componente bidireccional: manda los datos y recibe los clics
├── servicios/
│   ├── costos.py             # Motor de cálculo: costo de vida vs. costo total, colores
│   ├── rutas.py              # Red de hubs y ruta más barata con escalas
│   ├── turismo.py            # Ranking turístico (Wikipedia) y llegadas por país
│   ├── vuelos.py             # Orígenes + verificación Duffel
│   ├── travelpayouts.py      # Precios reales de búsquedas recientes (Aviasales) y enlaces de afiliado
│   ├── lugares.py            # Buscador mundial de ciudades y pueblos (GeoNames)
│   ├── alojamientos.py       # Proveedores de alojamiento (demo / Booking)
│   ├── tipos_cambio.py       # Conversión CLP/USD/EUR con caché y respaldo
│   ├── info_destino.py       # Fotos y resumen desde Wikipedia
│   └── cache.py              # Caché SQLite con fecha/hora y límite de llamadas
├── datos/destinos.json       # 1.512 destinos (se genera con scripts/generar_destinos.py)
├── datos/red_vuelos.pkl      # Red de vuelos precalculada (scripts/precalcular_red.py), acelera la primera carga
├── datos/ranking/*.txt       # Listas de destinos más turísticos por país (editables)
├── scripts/generar_destinos.py  # Regenera destinos.json a partir de las listas
├── scripts/precalcular_red.py   # Regenera datos/red_vuelos.pkl
├── .streamlit/config.toml    # Tema oscuro
├── .env.example
└── requirements.txt
```

## Cómo ampliarlo

- **Más destinos o cambiar el ranking base:** edita `datos/ranking/*.txt` (una línea por destino, en orden de popularidad) y ejecuta `python scripts/generar_destinos.py` y luego `python scripts/precalcular_red.py` (si se olvida el segundo, la app igual funciona: arma la red al vuelo, solo que la primera carga tarda un poco más). Para darle aeropuerto propio a un destino, agrégalo al diccionario `AEROPUERTOS` de ese script.
- **Más monedas:** agrega la moneda al diccionario `MONEDAS` en `servicios/tipos_cambio.py`.
- **Más orígenes:** agrega aeropuertos a `ORIGENES` en `servicios/vuelos.py`.
- **Etapa 2:**
  - Reemplazar `destinos.json` y `cache.db` por PostgreSQL + PostGIS.
  - Mover `servicios/` a un backend FastAPI; el motor de cálculo ya está separado de la interfaz.

## Velocidad y celulares

- **Primera carga más rápida:** la red de vuelos viene precalculada (`datos/red_vuelos.pkl`); el ranking de Wikipedia se consulta en segundo plano (mientras tanto se ve el ranking base y la página se actualiza sola al terminar); las consultas a Travelpayouts van en paralelo; la lista mundial de ciudades se descarga en segundo plano unos segundos después de abrir la app.
- **Celulares:** el globo se achica a la pantalla, la ficha sube desde abajo, la leyenda se pliega (se toca para abrirla), los botones van arriba a la derecha, "Calor vivo" parte apagado para ahorrar batería y el globo se dibuja con menos resolución. Los indicadores se ven en 2 columnas y las pestañas se deslizan de lado.

## Limitación conocida de Streamlit

El globo es un componente bidireccional de Streamlit hecho sin React (`componentes/globo_web/index.html`): recibe los datos por mensajes y devuelve a Python el último clic (destino, país o cierre de la ficha). Como Streamlit no permite cambiar de pestaña desde Python, un script mínimo hace clic en la pestaña que corresponde.
