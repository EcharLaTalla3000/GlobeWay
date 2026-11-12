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
  - Clic en un **país**: abre una ficha con sus destinos ordenados por precio.
  - Clic en un **punto**: desglose del viaje y un arco animado desde tu origen.
- **Colores**:
  - Modo *presupuesto* (por defecto): verde (≤60 %), amarillo (60–85 %), naranjo (85–100 %), violeta (hasta +15 %, ligeramente sobre) y rojo (fuera de presupuesto). Los destinos accesibles tienen un anillo pulsante.
  - Interruptor **Precios generales**: oculta el presupuesto y colorea cada destino según lo caro que es comparado con el resto del mundo (cuartiles), ya sea por costo total del viaje o por costo de vida en destino. La leyenda muestra los rangos de precio.
- Interruptor **Más turísticos**: mapa de calor 3D (columnas hexagonales) con las zonas más visitadas del mundo. La altura y el color de cada columna dependen de los turistas estimados en la zona: llegadas internacionales del país (cifra aproximada) × participación de cada destino.
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
4. **Booking.com:** la Demand API exige ser afiliado aprobado. El punto de conexión está preparado en `servicios/alojamientos.py` (`ProveedorBooking`), pero no está implementado, para no simular una API sin credenciales.

Nunca subas `.env` a un repositorio.

## Estructura

```
globeway/
├── app.py                    # Interfaz Streamlit (panel lateral, indicadores, pestañas)
├── componentes/
│   ├── globo.html            # Globo 3D (Globe.gl): países, puntos, arcos, ficha lateral
│   └── globo.py              # Inserta el globo en Streamlit con los datos calculados
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
├── datos/ranking/*.txt       # Listas de destinos más turísticos por país (editables)
├── scripts/generar_destinos.py  # Regenera destinos.json a partir de las listas
├── .streamlit/config.toml    # Tema oscuro
├── .env.example
└── requirements.txt
```

## Cómo ampliarlo

- **Más destinos o cambiar el ranking base:** edita `datos/ranking/*.txt` (una línea por destino, en orden de popularidad) y ejecuta `python scripts/generar_destinos.py`. Para darle aeropuerto propio a un destino, agrégalo al diccionario `AEROPUERTOS` de ese script.
- **Más monedas:** agrega la moneda al diccionario `MONEDAS` en `servicios/tipos_cambio.py`.
- **Más orígenes:** agrega aeropuertos a `ORIGENES` en `servicios/vuelos.py`.
- **Etapa 2:**
  - Reemplazar `destinos.json` y `cache.db` por PostgreSQL + PostGIS.
  - Mover `servicios/` a un backend FastAPI; el motor de cálculo ya está separado de la interfaz.

## Limitación conocida de Streamlit

El globo vive dentro de un iframe. La ficha que se abre al hacer clic funciona dentro del propio globo, pero el clic no cambia automáticamente el destino de las pestañas inferiores; ahí se elige con el selector. Para que el clic controle toda la página, en la Etapa 2 conviene pasar el frontend a React/Next.js.
