from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from garminconnect import GarminConnectAuthenticationError
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from swimops.auth import SessionNotFoundError, load_session
from swimops.config import (
    AthleteProfile,
    athlete_profile_path,
    load_athlete_profile,
    update_athlete_profile as write_athlete_profile,
)
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
    instructions="Local Garmin Connect activity and workout history.",
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
LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
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
        "message": "Run `uv run garmin login` locally and try again.",
    }


def _profile_result(profile: AthleteProfile | None) -> dict[str, Any]:
    values = profile.model_dump(exclude_none=True) if profile else {}
    missing = [
        field
        for field in AthleteProfile.model_fields
        if field not in values
    ]
    if not profile:
        status = "not_configured"
    elif missing:
        status = "incomplete"
    else:
        status = "configured"
    return {"status": status, "profile": values, "missing_fields": missing}


def _date(value: str, name: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must use YYYY-MM-DD format") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must use YYYY-MM-DD format")
    return parsed


@mcp.tool(annotations=GARMIN_READ_ONLY)
async def get_auth_status() -> dict[str, Any]:
    """Check whether a Garmin session is available without requesting credentials."""
    try:
        load_session()
    except (SessionNotFoundError, GarminConnectAuthenticationError):
        return _auth_required()
    return {"status": "authenticated"}


@mcp.tool(annotations=READ_ONLY)
async def get_athlete_profile() -> dict[str, Any]:
    """Return the local athlete preferences available to the coach."""
    path = athlete_profile_path()
    if not path.is_file():
        return _profile_result(None)
    return _profile_result(load_athlete_profile(path))


@mcp.tool(annotations=LOCAL_WRITE)
async def update_athlete_profile(
    pool_length_m: int | None = None,
    target_distance_m: int | None = None,
    swim_days_per_week: int | None = None,
    available_equipment: list[str] | None = None,
) -> dict[str, Any]:
    """Save user-provided athlete preferences in the local profile."""
    profile = write_athlete_profile(
        athlete_profile_path(),
        pool_length_m=pool_length_m,
        target_distance_m=target_distance_m,
        swim_days_per_week=swim_days_per_week,
        available_equipment=available_equipment,
    )
    return _profile_result(profile)


@mcp.tool(annotations=SYNC)
async def sync_activities(
    since: str, until: str | None = None
) -> dict[str, Any]:
    """Download a Garmin date range and process pool sessions locally."""
    start = _date(since, "since")
    end = _date(until, "until") if until else date.today()
    if start > end:
        raise ValueError("since cannot be later than until")
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
    """Show the latest sync and local data coverage."""
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
    """List recent activities with optional sport and inclusive date filters."""
    return _history().list_activities(sport, from_date, to_date, limit)


@mcp.tool(annotations=READ_ONLY)
async def get_activity(activity_id: int) -> dict[str, Any]:
    """Return an activity summary and pool metrics when available."""
    return _history().get_activity(activity_id)


@mcp.tool(annotations=READ_ONLY)
async def get_swim_history(
    from_date: str, to_date: str, limit: int = 30
) -> list[dict[str, Any]]:
    """Return compact pool session history for trend analysis."""
    return _history().get_swim_history(from_date, to_date, limit)


@mcp.tool(annotations=READ_ONLY)
async def get_swim_session(
    activity_id: int, include_lengths: bool = False
) -> dict[str, Any]:
    """Return a pool session summary, laps, and optionally every length."""
    return _history().get_swim_session(activity_id, include_lengths)


@mcp.tool(annotations=READ_ONLY)
async def preview_swim_workout(workout: dict[str, Any]) -> dict[str, Any]:
    """Validate and preview a workout proposal without writing to Garmin."""
    return workout_preview(SwimWorkout.model_validate(workout))


@mcp.tool(annotations=GARMIN_READ_ONLY)
async def list_workouts(limit: int = 20) -> list[dict[str, Any]]:
    """List Garmin Connect workouts without personal metadata."""
    return list_garmin_workouts(load_session(), limit)


@mcp.tool(annotations=GARMIN_READ_ONLY)
async def get_workout(workout_id: int) -> dict[str, Any]:
    """Return Garmin Connect workout details and segments."""
    return get_garmin_workout(load_session(), workout_id)


@mcp.tool(annotations=WRITE)
async def create_swim_workout(
    workout: dict[str, Any], confirmed: bool = False
) -> dict[str, Any]:
    """Create a Garmin workout only after preview and explicit approval."""
    if not confirmed:
        raise ValueError("explicit preview approval is required")
    return create_garmin_swim_workout(
        load_session(), SwimWorkout.model_validate(workout)
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
