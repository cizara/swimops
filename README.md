# swimops

CLI personal para autenticar en Garmin Connect y conservar localmente los FIT originales de las actividades.

Usa [`garminconnect`](https://github.com/cyberjunky/python-garminconnect), un cliente no oficial de los servicios web de Garmin Connect.

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

Sin `--until`, el rango termina en la fecha actual. Se incluyen todos los deportes. Los FIT originales quedan en `data/fit/<año>/<mes>/` y el índice mínimo en `data/garmin.sqlite`. Las ejecuciones posteriores omiten las actividades completas y reparan automáticamente un FIT o registro que falte.

El directorio de datos puede cambiarse sin alterar las fechas ni otros parámetros:

```bash
uv run garmin sync --since 2026-04-15 --data-dir /ruta/a/datos
```

El resumen final indica actividades descargadas, existentes y fallidas. Un fallo individual no detiene el resto; una ejecución posterior vuelve a intentarlo. El comando termina con código distinto de cero si alguna actividad falla.

Para elegir otro directorio de tokens, siempre fuera del repositorio:

```bash
GARMIN_TOKEN_DIR=/ruta/privada/garmin uv run garmin login
```

El directorio de tokens se crea con permisos `0700`; el archivo de tokens lo crea la librería con permisos `0600`. Debe tratarse como una contraseña. Si la sesión deja de ser válida, ejecuta `uv run garmin login` otra vez.

## Desarrollo

```bash
uv run pytest
```
