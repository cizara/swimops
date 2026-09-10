from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from swimops.auth import load_session
from swimops.queries import GarminHistory
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


def _history() -> GarminHistory:
    data_dir = Path(os.environ.get("GARMIN_DATA_DIR", "data")).expanduser()
    return GarminHistory(data_dir / "garmin.sqlite")


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
