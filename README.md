# VRP Optimizer

[![CI](https://github.com/Hector-RU/vrp-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/Hector-RU/vrp-optimizer/actions/workflows/ci.yml)

Aplicación de planificación logística con FastAPI, SQLAlchemy y OR-Tools. Permite gestionar pedidos y vehículos, planificar entregas con capacidad y ventanas horarias, consultar las rutas en un mapa y exportar el detalle en CSV.

## Ejecución local

Requiere Python 3.11 o 3.13. Desde PowerShell:

```powershell
git clone https://github.com/Hector-RU/vrp-optimizer.git
cd vrp-optimizer
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

En Linux/macOS, activa el entorno con `source .venv/bin/activate` y ejecuta los mismos comandos de instalación y arranque. Si PowerShell impide activar el entorno, puedes usar directamente `.venv\Scripts\python.exe` en lugar de `python`.

Abre `http://127.0.0.1:8000`. Las tablas se crean al iniciar, sin sustituir los datos existentes. La documentación interactiva de la API está en `/docs`; `/api/health` comprueba que el servidor responde.

## Flujo de uso

1. Registra primero el depósito con demanda **0**. El registro con menor ID se considera el depósito.
2. Añade los destinos y su demanda. Las ventanas se expresan en minutos desde medianoche: 480 corresponde a 08:00 y 1440 a 24:00.
3. Registra vehículos con capacidad positiva, en la misma unidad que la demanda.
4. En **Rutas**, pulsa **Generar rutas**. Todas las entregas deben poder asignarse; si las restricciones impiden una solución, se informa del error y se conserva la planificación anterior.
5. Consulta la distribución de carga y el mapa. Su selector de capas permite mostrar u ocultar vehículos. Exporta el detalle con **Exportar CSV**.

Crear, modificar o eliminar pedidos o vehículos invalida las rutas guardadas. Vuelve a generar la planificación después de esos cambios. **Cargar demostración** reemplaza todos los registros por datos de República Dominicana y solicita confirmación en la interfaz.

## Configuración

Las variables se leen del entorno. Para usar el archivo de ejemplo, copia `.env.example` a `.env` y arranca con `python -m uvicorn app.main:app --reload --env-file .env`. El archivo `.env` queda excluido de Git.

| Variable | Valor predeterminado | Uso |
| --- | --- | --- |
| `DATABASE_URL` | SQLite `vrp.db` en la raíz del proyecto | Conexión de base de datos |
| `VRP_TIME_LIMIT` | `30` | Tiempo máximo de búsqueda, en segundos |
| `VRP_STRATEGY` | `PARALLEL_CHEAPEST_INSERTION` | Estrategia inicial de OR-Tools |
| `MAP_DIR` | `app/static/maps` | Salida de mapas y caché vial |
| `LOG_LEVEL` | `INFO` | Nivel de registro |

Las rutas de recursos se resuelven desde el proyecto, independientemente del directorio de ejecución. Las escrituras se serializan dentro de un proceso para evitar cambios simultáneos durante la planificación. Ejecuta una sola instancia local; una instalación con varios procesos necesitaría coordinación compartida y autenticación.

## Pruebas

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check app/static/js/app.js
```

Node.js 22 se utiliza únicamente para comprobar la sintaxis del JavaScript; la aplicación no requiere Node.js para ejecutarse. GitHub Actions ejecuta estas comprobaciones en Linux y Windows con Python 3.11 y 3.13 en cada push y pull request. Las dependencias directas tienen versiones fijadas en `requirements.txt`, las herramientas de pruebas en `requirements-dev.txt` y las dependencias indirectas en `constraints.txt`. Al actualizar dependencias, actualiza también las restricciones y ejecuta las pruebas.

Las pruebas usan SQLite en memoria, un tiempo de búsqueda de un segundo (cinco en el escenario completo de demostración) y simulaciones de OSRM para las verificaciones de mapas. No utilizan `vrp.db` ni `test.db` y no necesitan acceso externo.

## Supuestos y límites

- La distancia optimizada se calcula con Haversine, en línea recta. El mapa solicita geometría vial a OSRM; estas dos distancias pueden diferir.
- La duración de planificación incluye trayectos y esperas por ventanas horarias. No modela carga/descarga ni tráfico en tiempo real.
- El modelo ETA incluido se entrenó con datos sintéticos de 1 a 50 km. Se usa una referencia fija de lunes a las 09:00 para resultados reproducibles. Si el modelo es incompatible con la versión instalada de scikit-learn, falta o la distancia queda fuera del rango de entrenamiento, se utiliza una estimación de `2.5 × km + 5` minutos.
- OSRM tiene un tiempo de espera de cinco segundos por petición y hasta cinco peticiones simultáneas por ruta. Si falla, el mapa conecta las paradas en línea recta; no se informa distancia cero como si fuera un trayecto válido.
- Mapas, fuentes, iconos y gráficos usan servicios/CDN externos. Si Chart.js no está disponible, las tablas y la gestión continúan funcionando.
- El traslado manual está disponible por API: `POST /api/routes/swap-stops` recibe JSON con `from_vehicle`, `to_vehicle` y `stop_id`. Comprueba capacidad y horarios, mantiene el retorno al depósito y recalcula métricas antes de guardar.

Para regenerar el modelo ETA con las dependencias instaladas, ejecuta `python -m app.ml.train_eta`. Esto reemplaza `app/ml/eta_model.joblib`. Las bases de datos, mapas y cachés generados se excluyen de Git; cada instalación comienza con una base vacía y puede cargar datos desde **Cargar demostración**.

## Estructura

```text
app/api/             Endpoints de pedidos, flota y planificación
app/db/              Persistencia y validación
app/vrp/             Solucionador con restricciones
app/ml/              Estimación de duración y entrenamiento sintético
app/visualization/   Geometría vial y mapas
app/static/          Interfaz, estilos y JavaScript
tests/               Pruebas de API y regresiones
```
