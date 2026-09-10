# Garmin Swim Agent — Plan de proyecto

## Objetivo

Construir una herramienta personal que permita:

1. Descargar y persistir actividades de Garmin Connect.
2. Analizar principalmente sesiones de natación.
3. Mantener los archivos FIT originales como fuente de verdad.
4. Generar resúmenes estructurados para consultas y análisis con agentes.
5. Crear rutinas nuevas de natación mediante un agente.
6. Subir y programar esas rutinas en Garmin Connect para que lleguen al reloj.

El MVP se centrará en **natación**. Fútbol podrá reutilizar la misma infraestructura más adelante.

---

## Enfoque elegido

Tomar `goosegit97/garmin-mcp` como referencia/base para la parte de creación y programación de workouts de natación.

Completarlo con una capa propia para:

- listar actividades;
- descargar actividades;
- descargar FIT;
- parsear FIT;
- persistir métricas;
- exponer un histórico compacto al agente.

Arquitectura objetivo:

```text
                         Garmin Connect
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
         Activity sync                 Workout API
                │                           │
                ▼                           │
        archivos FIT                        │
                │                           │
                ▼                           │
          FIT parser                        │
                │                           │
                ▼                           │
             SQLite                         │
                │                           │
                └──────────┬────────────────┘
                           ▼
                       MCP Server
                           │
                           ▼
                         Agent
```

---

# Fase 1 — MVP

## 1. Autenticación con Garmin Connect

Implementar login y persistencia de sesión/tokens.

Objetivo:

```bash
garmin login
```

La autenticación debe quedar persistida localmente para evitar introducir credenciales en cada ejecución.

### Criterio de terminado

- autenticación funcional;
- tokens almacenados fuera del repositorio;
- reautenticación cuando expiren.

---

## 2. Sincronización de actividades

Agregar capacidad para listar actividades de Garmin Connect.

Comando inicial:

```bash
garmin activities
```

Después:

```bash
garmin sync
garmin sync --since 2026-01-01
```

Inicialmente interesan:

- natación;
- fútbol;
- eventualmente running/ciclismo.

### Datos mínimos

Por actividad:

- Garmin activity ID;
- fecha;
- deporte;
- duración;
- distancia;
- nombre;
- frecuencia cardíaca media;
- frecuencia cardíaca máxima.

---

## 3. Descargar FIT

Cada actividad sincronizada debe conservar su FIT original.

Estructura:

```text
data/
└── fit/
    └── 2026/
        └── 09/
            └── <activity-id>.fit
```

Regla:

> El FIT es la fuente de verdad y nunca se modifica.

La base de datos contiene únicamente datos derivados o indexados.

### Criterio de terminado

```bash
garmin sync
```

debe:

1. buscar actividades nuevas;
2. descargar su FIT;
3. evitar duplicados;
4. registrar la actividad en la base.

---

## 4. Parsear natación

Extraer del FIT las métricas útiles para analizar sesiones.

Prioridad inicial:

### Sesión

- distancia total;
- duración;
- moving time;
- pool length;
- ritmo medio / 100 m;
- HR media;
- HR máxima;
- tiempo por zona cardíaca;
- SWOLF medio;
- strokes totales;
- strokes por largo.

### Laps / sets

- distancia;
- duración;
- pace;
- stroke type;
- strokes;
- SWOLF.

### Lengths

Si FIT ofrece datos fiables:

- número de largo;
- distancia;
- duración;
- stroke type;
- strokes;
- SWOLF.

No hace falta extraer todos los campos FIT disponibles.

---

## 5. Persistencia

Usar **SQLite**.

Archivo:

```text
data/garmin.sqlite
```

Modelo inicial:

```text
activities
----------
id
garmin_id
date
sport
name
fit_path
duration_s
distance_m
avg_hr
max_hr

swim_sessions
-------------
activity_id
pool_length_m
total_lengths
avg_pace_100m
avg_swolf
avg_strokes_per_length

swim_laps
---------
activity_id
lap_index
distance_m
duration_s
pace_100m
stroke_type
stroke_count
swolf

hr_zones
--------
activity_id
zone
seconds
```

No duplicar en SQLite todo lo que exista en FIT.

---

# Fase 2 — MCP para análisis

Exponer datos procesados al agente mediante tools simples.

## Tools

### `list_activities`

```text
list_activities(
    sport?,
    from?,
    to?,
    limit?
)
```

---

### `get_activity`

Devuelve el resumen completo de una actividad.

```text
get_activity(activity_id)
```

---

### `get_swim_history`

Tool principal para análisis.

```text
get_swim_history(
    from,
    to,
    limit?
)
```

Debe devolver información compacta.

Ejemplo:

```json
{
  "date": "2026-09-09",
  "distance_m": 2200,
  "duration_s": 3120,
  "avg_pace_100m": 112,
  "avg_swolf": 38,
  "avg_hr": 138,
  "max_hr": 167,
  "zones": {
    "z1": 420,
    "z2": 980,
    "z3": 1150,
    "z4": 510,
    "z5": 60
  }
}
```

Evitar enviar FIT completos al LLM salvo que sea necesario.

---

### `get_swim_session`

Devuelve detalle de una sesión:

- resumen;
- laps;
- sets;
- lengths opcionales.

---

# Fase 3 — Generación de workouts

Estado:

- [x] Schema propio, validación y vista previa local/MCP.
- [x] Listado y detalle de workouts existentes en Garmin Connect.
- [x] Conversión al formato de Garmin y creación con confirmación explícita.
- [x] Validación real con una rutina aprobada por el usuario.
- [ ] Programación del workout en una fecha.

Reutilizar la lógica de `goosegit97/garmin-mcp`.

El agente **no genera directamente el JSON interno de Garmin**.

Definimos un schema propio.

Ejemplo:

```json
{
  "name": "CSS intervals",
  "sport": "swimming",
  "pool_length_m": 25,
  "steps": [
    {
      "type": "warmup",
      "distance_m": 400
    },
    {
      "repeat": 8,
      "steps": [
        {
          "type": "swim",
          "distance_m": 100,
          "stroke": "freestyle",
          "target": {
            "type": "pace",
            "pace": "1:45"
          }
        },
        {
          "type": "rest",
          "duration_s": 20
        }
      ]
    },
    {
      "type": "cooldown",
      "distance_m": 300
    }
  ]
}
```

Pipeline:

```text
Agent
  ↓
workout JSON propio
  ↓
schema validation
  ↓
Garmin workout builder
  ↓
Garmin Connect
  ↓
Garmin watch
```

---

## MCP tools de workouts

### `create_swim_workout`

Crea el workout en Garmin Connect.

---

### `schedule_workout`

Asigna el workout a una fecha.

---

### `list_workouts`

Lista workouts existentes.

---

### `get_workout`

Obtiene detalle de un workout.

---

# Fase 4 — Análisis inteligente

Una vez que existe suficiente histórico, el agente podrá responder cosas como:

- ¿Estoy mejorando mi ritmo en series de 100 m?
- ¿Cómo evolucionó mi SWOLF?
- Compará mis últimas 10 sesiones de 2 km.
- ¿Estoy entrenando demasiado en Z4/Z5?
- ¿Qué estilos estoy entrenando poco?
- Generame una sesión de 2400 m basada en mis últimas semanas.
- Quiero trabajar técnica sin subir demasiado la carga.
- Preparame tres sesiones para esta semana.

---

# Fase 5 — Planificación

Agregar contexto temporal.

Por ejemplo:

```text
get_training_history(days=30)
```

y eventualmente:

```text
get_upcoming_workouts()
```

El agente podrá considerar:

- carga reciente;
- sesiones anteriores;
- descanso;
- distancia semanal;
- intensidad;
- distribución por zonas;
- objetivo del usuario.

Podría generar algo como:

```text
martes
  técnica + aeróbico
  2200 m

jueves
  CSS / threshold
  2400 m

sábado
  fondo
  2800 m
```

---

# Fase 6 — Fútbol

Reutilizar la infraestructura existente.

Agregar:

```text
football_sessions
-----------------
activity_id
duration_s
distance_m
avg_hr
max_hr
z1_s
z2_s
z3_s
z4_s
z5_s
```

Inicialmente no hace falta modelar el fútbol con el mismo detalle que la natación.

El agente podría usarlo para evitar generar un entrenamiento duro de natación después de un partido muy intenso.

---

# Estructura del proyecto

Propuesta inicial:

```text
garmin-agent/
├── README.md
├── pyproject.toml
│
├── data/
│   ├── garmin.sqlite
│   └── fit/
│
├── src/
│   └── garmin_agent/
│       ├── garmin/
│       │   ├── auth.py
│       │   ├── activities.py
│       │   ├── download.py
│       │   └── workouts.py
│       │
│       ├── fit/
│       │   ├── parser.py
│       │   └── swimming.py
│       │
│       ├── db/
│       │   ├── models.py
│       │   └── repository.py
│       │
│       ├── mcp/
│       │   ├── activities.py
│       │   ├── swimming.py
│       │   └── workouts.py
│       │
│       └── cli.py
│
└── tests/
```

---

# Orden de implementación

## MVP 0

Garmin Connect:

```text
login
↓
list activities
↓
download FIT
```

---

## MVP 1

```text
download FIT
↓
parse FIT
↓
SQLite
```

Resultado:

```bash
garmin sync
```

---

## MVP 2

MCP read-only:

```text
list_activities
get_activity
get_swim_history
get_swim_session
```

Ya permite usar un agente para analizar los entrenamientos.

---

## MVP 3

MCP write:

```text
create_swim_workout
schedule_workout
```

Ya permite:

```text
histórico
    ↓
agent
    ↓
nueva rutina
    ↓
Garmin Connect
    ↓
reloj
```

Este es el **primer MVP completo**.

---

# Decisiones técnicas

## Lenguaje

Preferencia inicial: **Python**.

Motivos:

- ecosistema FIT;
- SQLite;
- análisis de datos;
- integración sencilla con agentes;
- `python-garminconnect`;
- MCP SDK.

Aunque `goosegit97/garmin-mcp` esté escrito en Go, puede usarse como referencia para reproducir la lógica necesaria en Python.

---

## Source of truth

```text
FIT = actividad original
SQLite = datos procesados
```

---

## Schema de workouts

Mantener un schema propio independiente de Garmin.

Nunca hacer depender al agente directamente del formato interno de Garmin Connect.

---

## API de Garmin

Para el MVP personal:

```text
Garmin Connect unofficial API
```

Si el proyecto algún día se convierte en producto:

```text
Garmin Activity API
Garmin Training API
```

La capa de análisis, SQLite, FIT y schema propio deberían poder mantenerse sin grandes cambios.

---

# Riesgos

## Garmin Connect no oficial

Garmin puede modificar endpoints internos.

Mitigación:

- encapsular todo acceso a Garmin detrás de `garmin/`;
- mantener FIT como formato local;
- no mezclar lógica Garmin con análisis.

---

## FIT de natación

Algunas métricas pueden variar por dispositivo o firmware.

Mitigación:

- probar inicialmente con actividades reales del reloj;
- mantener FIT originales;
- parsear únicamente campos necesarios.

---

## Alucinaciones del agente

El LLM no debe producir directamente payloads Garmin.

Mitigación:

```text
LLM
↓
schema propio
↓
validation
↓
builder determinístico
```

---

# Definición del MVP completo

El MVP está terminado cuando se pueda hacer lo siguiente:

```text
1. Hago una sesión de natación.

2. Garmin la sincroniza.

3. Ejecuto:

   garmin sync

4. El FIT queda almacenado.

5. Las métricas relevantes quedan en SQLite.

6. Pregunto al agente:

   "Analizá mis últimas 10 sesiones y preparame
    una rutina de 2400 m para trabajar velocidad."

7. El agente consulta el histórico.

8. Genera un workout estructurado.

9. Lo crea en Garmin Connect.

10. Lo programa para mañana.

11. Garmin lo sincroniza con el reloj.
```

Ese flujo constituye el objetivo principal del proyecto.
