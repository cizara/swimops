from __future__ import annotations

from typing import Any

from garminconnect import Garmin


def get_activities(client: Garmin, limit: int) -> list[dict[str, Any]]:
    return client.get_activities(0, limit)


def format_activities(activities: list[dict[str, Any]]) -> str:
    lines = ["ID\tFECHA\tDEPORTE\tDISTANCIA_M\tDURACION_S\tNOMBRE"]
    for activity in activities:
        activity_type = activity.get("activityType") or {}
        values = (
            activity.get("activityId", ""),
            activity.get("startTimeLocal", activity.get("startTimeGMT", "")),
            activity_type.get("typeKey", ""),
            _number(activity.get("distance")),
            _number(activity.get("duration")),
            _clean(activity.get("activityName", "")),
        )
        lines.append("\t".join(map(str, values)))
    return "\n".join(lines)


def _number(value: Any) -> str:
    if not isinstance(value, int | float):
        return ""
    return f"{value:.0f}"


def _clean(value: Any) -> str:
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
