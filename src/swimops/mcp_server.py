from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from garminconnect import GarminConnectAuthenticationError
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from swimops.auth import SessionNotFoundError, load_session
from swimops.processing import parse_swims
from swimops.queries import GarminHistory
from swimops.sync import sync_activities as run_sync
from swimops.workouts import (
    SwimWorkout,
    create_garmin_swim_workout,
    get_garmin_workout,
    list_garmin_workouts,
    workout_preview,
)


mcp = MCPServer(
    "swimops",
    instructions="Histórico local de actividades y workouts de Garmin Connect.",
)
GARMIN_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
SYNC = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _history() -> GarminHistory:
    return GarminHistory(_data_dir() / "garmin.sqlite")


def _data_dir() -> Path:
    return Path(os.environ.get("GARMIN_DATA_DIR", "data")).expanduser()


def _auth_required() -> dict[str, Any]:
    return {
        "status": "auth_required",
        "message": "Ejecuta localmente `uv run garmin login` y vuelve a intentarlo.",
    }


def _date(value: str, name: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} debe tener formato YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{name} debe tener formato YYYY-MM-DD")
    return parsed


@mcp.tool(annotations=GARMIN_READ_ONLY)
async def get_auth_status() -> dict[str, Any]:
    """Comprueba si la sesión de Garmin está disponible sin solicitar credenciales."""
    try:
        load_session()
    except (SessionNotFoundError, GarminConnectAuthenticationError):
        return _auth_required()
    return {"status": "authenticated"}


@mcp.tool(annotations=SYNC)
async def sync_activities(
    since: str, until: str | None = None
) -> dict[str, Any]:
    """Descarga un rango de Garmin y procesa las sesiones de piscina localmente."""
    start = _date(since, "since")
    end = _date(until, "until") if until else date.today()
    if start > end:
        raise ValueError("since no puede ser posterior a until")
    try:
        client = load_session()
        summary = run_sync(client, start, end, _data_dir())
    except (SessionNotFoundError, GarminConnectAuthenticationError):
        return _auth_required()

    data_dir = _data_dir()
    parsed = parse_swims(data_dir)
    return {
        "status": "completed" if not summary.failed and not parsed.failed else "partial",
        "since": start.isoformat(),
        "until": end.isoformat(),
        "activities": {
            "downloaded": summary.downloaded,
            "existing": summary.existing,
            "failed": summary.failed,
        },
        "swims": {
            "parsed": parsed.parsed,
            "existing": parsed.existing,
            "failed": parsed.failed,
        },
    }


@mcp.tool(annotations=READ_ONLY)
async def get_sync_status() -> dict[str, Any]:
    """Muestra la última sincronización y la cobertura de los datos locales."""
    try:
        return {"status": "available", **_history().get_sync_status()}
    except FileNotFoundError:
        return {"status": "not_synced"}


@mcp.tool(annotations=READ_ONLY)
async def list_activities(
    sport: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Lista actividades recientes, con filtros opcionales de deporte y fechas inclusivas."""
    return _history().list_activities(sport, from_date, to_date, limit)


@mcp.tool(annotations=READ_ONLY)
async def get_activity(activity_id: int) -> dict[str, Any]:
    """Devuelve el resumen de una actividad y métricas de piscina cuando existen."""
    return _history().get_activity(activity_id)


@mcp.tool(annotations=READ_ONLY)
async def get_swim_history(
    from_date: str, to_date: str, limit: int = 30
) -> list[dict[str, Any]]:
    """Devuelve un histórico compacto de sesiones de piscina para analizar tendencias."""
    return _history().get_swim_history(from_date, to_date, limit)


@mcp.tool(annotations=READ_ONLY)
async def get_swim_session(
    activity_id: int, include_lengths: bool = False
) -> dict[str, Any]:
    """Devuelve resumen, laps y, opcionalmente, cada largo de una sesión de piscina."""
    return _history().get_swim_session(activity_id, include_lengths)


@mcp.tool(annotations=READ_ONLY)
async def preview_swim_workout(workout: dict[str, Any]) -> dict[str, Any]:
    """Valida una propuesta de rutina y devuelve una vista previa; no escribe en Garmin."""
    return workout_preview(SwimWorkout.model_validate(workout))


@mcp.tool(annotations=GARMIN_READ_ONLY)
async def list_workouts(limit: int = 20) -> list[dict[str, Any]]:
    """Lista workouts de Garmin Connect sin incluir metadatos personales."""
    return list_garmin_workouts(load_session(), limit)


@mcp.tool(annotations=GARMIN_READ_ONLY)
async def get_workout(workout_id: int) -> dict[str, Any]:
    """Devuelve el detalle y los segmentos de un workout de Garmin Connect."""
    return get_garmin_workout(load_session(), workout_id)


@mcp.tool(annotations=WRITE)
async def create_swim_workout(
    workout: dict[str, Any], confirmed: bool = False
) -> dict[str, Any]:
    """Crea una rutina en Garmin sólo después de mostrarla y recibir aprobación explícita."""
    if not confirmed:
        raise ValueError("falta aprobación explícita de la vista previa")
    return create_garmin_swim_workout(
        load_session(), SwimWorkout.model_validate(workout)
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
