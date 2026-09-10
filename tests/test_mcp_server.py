import asyncio
from datetime import date
from pathlib import Path

import pytest
from mcp import Client

from swimops import mcp_server
from swimops.auth import SessionNotFoundError
from swimops.mcp_server import mcp
from swimops.processing import ParseSummary
from swimops.repository import Activity, ActivityRepository
from swimops.sync import SyncSummary


def test_exposes_read_only_history_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        repository.register(
            Activity(123, "2026-09-09", "soccer", "Match", Path("activity.fit"))
        )
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))

    async def check_server() -> None:
        async with Client(mcp, mode="legacy") as client:
            tools = await client.list_tools()
            result = await client.call_tool("list_activities", {"limit": 10})
            preview = await client.call_tool(
                "preview_swim_workout",
                {
                    "workout": {
                        "name": "Suave",
                        "pool_length_m": 25,
                        "steps": [{"type": "swim", "distance_m": 500}],
                    }
                },
            )

        assert {tool.name for tool in tools.tools} == {
            "get_auth_status",
            "sync_activities",
            "get_sync_status",
            "list_activities",
            "get_activity",
            "get_swim_history",
            "get_swim_session",
            "preview_swim_workout",
            "list_workouts",
            "get_workout",
            "create_swim_workout",
        }
        annotations = {tool.name: tool.annotations for tool in tools.tools}
        assert annotations["create_swim_workout"].read_only_hint is False
        assert annotations["sync_activities"].read_only_hint is False
        assert all(
            annotation.read_only_hint
            for name, annotation in annotations.items()
            if name not in {"create_swim_workout", "sync_activities"}
        )
        assert result.structured_content == {
            "result": [
                {
                    "activity_id": 123,
                    "date": "2026-09-09",
                    "sport": "soccer",
                    "name": "Match",
                }
            ]
        }
        assert preview.structured_content["total_distance_m"] == 500

    asyncio.run(check_server())


def test_exposes_remote_workouts_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GarminClient:
        def get_workouts(self, start: int, limit: int):
            return [
                {
                    "workoutId": 123,
                    "workoutName": "Día A",
                    "sportType": {"sportTypeKey": "swimming"},
                    "estimatedDistanceInMeters": 1500,
                    "poolLength": 25,
                }
            ]

        def upload_workout(self, payload):
            return {"workoutId": 456, "workoutName": payload["workoutName"]}

    monkeypatch.setattr(mcp_server, "load_session", GarminClient)

    async def check_server() -> None:
        async with Client(mcp, mode="legacy") as client:
            result = await client.call_tool("list_workouts", {"limit": 5})
            created = await client.call_tool(
                "create_swim_workout",
                {
                    "workout": {
                        "name": "Suave",
                        "pool_length_m": 25,
                        "steps": [{"type": "swim", "distance_m": 500}],
                    },
                    "confirmed": True,
                },
            )
            rejected = await client.call_tool(
                "create_swim_workout",
                {
                    "workout": {
                        "name": "Sin aprobar",
                        "pool_length_m": 25,
                        "steps": [{"type": "swim", "distance_m": 500}],
                    }
                },
            )

        assert result.structured_content["result"][0]["workout_id"] == 123
        assert created.structured_content["workout_id"] == 456
        assert rejected.is_error

    asyncio.run(check_server())


def test_sync_reports_when_local_login_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_session():
        raise SessionNotFoundError("missing")

    monkeypatch.setattr(mcp_server, "load_session", missing_session)

    async def check_server() -> None:
        async with Client(mcp, mode="legacy") as client:
            auth = await client.call_tool("get_auth_status", {})
            sync = await client.call_tool(
                "sync_activities",
                {"since": "2026-04-15", "until": "2026-09-10"},
            )

        assert auth.structured_content["status"] == "auth_required"
        assert sync.structured_content["status"] == "auth_required"
        assert "garmin login" in sync.structured_content["message"]

    asyncio.run(check_server())


def test_sync_downloads_and_processes_swims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    garmin = object()
    calls = []
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(mcp_server, "load_session", lambda: garmin)

    def sync(client, since, until, data_dir):
        calls.append((client, since, until, data_dir))
        return SyncSummary(downloaded=2, existing=3)

    monkeypatch.setattr(mcp_server, "run_sync", sync)
    monkeypatch.setattr(
        mcp_server,
        "parse_swims",
        lambda data_dir: ParseSummary(parsed=1, existing=4),
    )

    async def check_server() -> None:
        async with Client(mcp, mode="legacy") as client:
            result = await client.call_tool(
                "sync_activities",
                {"since": "2026-04-15", "until": "2026-09-10"},
            )

        assert result.structured_content == {
            "status": "completed",
            "since": "2026-04-15",
            "until": "2026-09-10",
            "activities": {"downloaded": 2, "existing": 3, "failed": 0},
            "swims": {"parsed": 1, "existing": 4, "failed": 0},
        }

    asyncio.run(check_server())
    assert calls == [(garmin, date(2026, 4, 15), date(2026, 9, 10), tmp_path)]
