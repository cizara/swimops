import asyncio
from pathlib import Path

import pytest
from mcp import Client

from swimops import mcp_server
from swimops.mcp_server import mcp
from swimops.repository import Activity, ActivityRepository


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
        assert all(
            annotation.read_only_hint
            for name, annotation in annotations.items()
            if name != "create_swim_workout"
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
