# swimops

CLI personal para autenticar en Garmin Connect y conservar localmente los FIT originales de las actividades.

Usa [`garminconnect`](https://github.com/cyberjunky/python-garminconnect), un cliente no oficial de los servicios web de Garmin Connect, y el [SDK FIT oficial de Garmin](https://github.com/garmin/fit-python-sdk).

## Requisitos e instalación

- [`uv`](https://docs.astral.sh/uv/)
- Python 3.12 o posterior (lo gestiona `uv` si hace falta)

```bash
uv sync
```

## Uso

Inicia sesión de forma interactiva:

```bash
uv run garmin login
```

La contraseña y el código MFA, si corresponde, no se muestran ni se guardan. Los tokens se persisten fuera del repositorio en `~/.local/share/swimops/garmin/garmin_tokens.json` y se reutilizan en ejecuciones posteriores.

Lista las diez actividades más recientes, o cambia el límite:

```bash
uv run garmin activities
uv run garmin activities --limit 25
```

Descarga y registra todas las actividades de un rango inclusivo:

```bash
uv run garmin sync --since 2026-04-15
uv run garmin sync --since 2026-04-15 --until 2026-09-09
```

Sin `--until`, el rango termina en la fecha actual. Se incluyen todos los deportes. Los FIT originales quedan en `data/fit/<año>/<mes>/` y el índice en `data/garmin.sqlite`. Las sesiones de piscina se procesan automáticamente. Las ejecuciones posteriores omiten las actividades completas y reparan automáticamente un FIT o registro que falte.

El directorio de datos puede cambiarse sin alterar las fechas ni otros parámetros:

```bash
uv run garmin sync --since 2026-04-15 --data-dir /ruta/a/datos
```

El resumen final indica actividades descargadas, existentes y fallidas. Un fallo individual no detiene el resto; una ejecución posterior vuelve a intentarlo. El comando termina con código distinto de cero si alguna actividad falla.

Procesa los FIT de natación en piscina ya descargados:

```bash
uv run garmin parse-swims
```

El comando guarda en SQLite el resumen de cada sesión, laps, largos y tiempos por zona cardíaca. Ritmo medio usa el tiempo activo de nado; SWOLF se calcula por largo como segundos más brazadas. Las zonas se conservan con los índices presentes en el FIT, incluido el tiempo por debajo y por encima de las cinco zonas configuradas.

Las sesiones procesadas se omiten en ejecuciones posteriores. Para recalcularlas después de cambiar el parser:

```bash
uv run garmin parse-swims --force
```

## MCP read-only

El servidor local expone `list_activities`, `get_activity`, `get_swim_history` y `get_swim_session` por `stdio`:

```bash
uv run garmin-mcp
```

Configuración genérica para un host MCP:

```json
{
  "mcpServers": {
    "swimops": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/lucho/web/cizara/swimops",
        "run",
        "garmin-mcp"
      ],
      "env": {
        "GARMIN_DATA_DIR": "/home/lucho/web/cizara/swimops/data"
      }
    }
  }
}
```

Otro usuario sólo necesita cambiar ambas rutas. El servidor consulta SQLite localmente y no contacta Garmin Connect.

## Propuestas de workouts

Una rutina puede validarse y revisarse localmente antes de crearla en Garmin:

```bash
uv run garmin workout-preview examples/swim-workout.json
```

El formato admite calentamiento, nado, descansos, repeticiones, vuelta a la calma, estilo, material, técnica, notas y un objetivo de ritmo único por bloque. La longitud de piscina forma parte de cada propuesta y todas las distancias deben ser múltiplos de ella. La vista previa muestra la distancia total y el descanso programado.

El MCP expone también `preview_swim_workout`. Esta herramienta sólo valida y presenta la propuesta; no contacta Garmin ni crea workouts.

Los workouts existentes pueden consultarse sin modificarlos:

```bash
uv run garmin workouts
uv run garmin workout 1675490181
```

El MCP ofrece las mismas consultas mediante `list_workouts` y `get_workout`. Estas dos herramientas leen Garmin Connect usando la sesión local guardada.

Después de revisar la vista previa, la creación exige confirmación explícita:

```bash
uv run garmin workout-create examples/swim-workout.json --confirm
```

En MCP, `create_swim_workout` requiere `confirmed=true`. Debe usarse únicamente después de mostrar `preview_swim_workout` y recibir aprobación del usuario. La creación guarda el workout en Garmin Connect; no lo programa todavía.

Para elegir otro directorio de tokens, siempre fuera del repositorio:

```bash
GARMIN_TOKEN_DIR=/ruta/privada/garmin uv run garmin login
```

El directorio de tokens se crea con permisos `0700`; el archivo de tokens lo crea la librería con permisos `0600`. Debe tratarse como una contraseña. Si la sesión deja de ser válida, ejecuta `uv run garmin login` otra vez.

## Desarrollo

```bash
uv run pytest
```
