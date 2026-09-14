from __future__ import annotations

import sqlite3
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any


def routine_key(name: str) -> str:
    prefix = name.split(":", 1)[0].strip()
    normalized = unicodedata.normalize("NFKD", prefix)
    plain = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(plain.casefold().split())


def summarize_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    distance = sum(session["distance_m"] or 0 for session in sessions)
    swim_time = sum(session["swim_time_s"] or 0 for session in sessions)
    elapsed_time = sum(session["elapsed_time_s"] or 0 for session in sessions)

    def weighted(field: str, weight: str) -> float | None:
        rows = [
            session
            for session in sessions
            if session[field] is not None and (session[weight] or 0) > 0
        ]
        total_weight = sum(session[weight] for session in rows)
        if not total_weight:
            return None
        return sum(session[field] * session[weight] for session in rows) / total_weight

    return {
        "sessions": len(sessions),
        "distance_m": distance,
        "swim_time_s": swim_time,
        "elapsed_time_s": elapsed_time,
        "avg_pace_100m_s": swim_time * 100 / distance if distance else None,
        "avg_swolf": weighted("avg_swolf", "distance_m"),
        "avg_strokes_per_length": weighted(
            "avg_strokes_per_length", "distance_m"
        ),
        "avg_hr": weighted("avg_hr", "swim_time_s"),
    }


class SwimReports:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def list_routines(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.name, substr(a.activity_date, 1, 10) AS activity_date
                FROM activities a
                JOIN swim_sessions s ON s.activity_id = a.garmin_id
                ORDER BY a.activity_date DESC
                """
            ).fetchall()

        routines: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = routine_key(row["name"])
            if key not in routines:
                routines[key] = {
                    "key": key,
                    "name": row["name"].split(":", 1)[0].strip(),
                    "sessions": 0,
                    "first_date": row["activity_date"],
                    "last_date": row["activity_date"],
                }
            routine = routines[key]
            routine["sessions"] += 1
            routine["first_date"] = min(routine["first_date"], row["activity_date"])
        return sorted(routines.values(), key=lambda item: item["last_date"], reverse=True)

    def activities(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        start = _date(from_date)
        end = _date(to_date)
        if start > end:
            raise ValueError("from_date cannot be later than to_date")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT garmin_id AS activity_id,
                       substr(activity_date, 1, 10) AS date,
                       sport, name, distance_m, duration_s
                FROM activities
                WHERE substr(activity_date, 1, 10) BETWEEN ? AND ?
                ORDER BY activity_date
                """,
                (from_date, to_date),
            ).fetchall()
        return [dict(row) for row in rows]

    def sessions(
        self,
        from_date: str,
        to_date: str,
        routines: list[str] | None = None,
        main_only: bool = False,
    ) -> list[dict[str, Any]]:
        start = _date(from_date)
        end = _date(to_date)
        if start > end:
            raise ValueError("from_date cannot be later than to_date")
        query = _MAIN_SESSIONS if main_only else _FULL_SESSIONS
        with self._connect() as connection:
            rows = connection.execute(query, (from_date, to_date)).fetchall()

        selected = set(routines or [])
        result = []
        for row in rows:
            session = dict(row)
            session["routine"] = routine_key(session["name"])
            if not selected or session["routine"] in selected:
                result.append(session)
        return result

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise FileNotFoundError(f"Database does not exist: {self.database_path}")
        connection = sqlite3.connect(
            f"{self.database_path.resolve().as_uri()}?mode=ro", uri=True
        )
        connection.row_factory = sqlite3.Row
        return connection


def _date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Dates must use YYYY-MM-DD format") from error
    if parsed.isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD format")
    return parsed


_FULL_SESSIONS = """
    SELECT a.garmin_id AS activity_id,
           substr(a.activity_date, 1, 10) AS date,
           a.name,
           s.distance_m,
           s.elapsed_time_s,
           s.timer_time_s,
           s.swim_time_s,
           s.avg_pace_100m AS avg_pace_100m_s,
           s.avg_swolf,
           s.avg_strokes_per_length,
           s.avg_hr,
           s.max_hr
    FROM swim_sessions s
    JOIN activities a ON a.garmin_id = s.activity_id
    WHERE substr(a.activity_date, 1, 10) BETWEEN ? AND ?
    ORDER BY a.activity_date
"""


_MAIN_SESSIONS = """
    WITH step_bounds AS (
        SELECT activity_id,
               COUNT(DISTINCT workout_step_index) AS step_count,
               MIN(workout_step_index) AS first_step,
               MAX(workout_step_index) AS last_step
        FROM swim_laps
        WHERE distance_m > 0 AND workout_step_index IS NOT NULL
        GROUP BY activity_id
    )
    SELECT a.garmin_id AS activity_id,
           substr(a.activity_date, 1, 10) AS date,
           a.name,
           SUM(l.distance_m) AS distance_m,
           SUM(l.elapsed_time_s) AS elapsed_time_s,
           SUM(l.timer_time_s) AS timer_time_s,
           SUM(l.swim_time_s) AS swim_time_s,
           CASE WHEN SUM(l.distance_m) > 0
                THEN SUM(l.swim_time_s) * 100.0 / SUM(l.distance_m) END
                AS avg_pace_100m_s,
           CASE WHEN SUM(CASE WHEN l.avg_swolf IS NOT NULL THEN l.active_lengths ELSE 0 END) > 0
                THEN SUM(l.avg_swolf * l.active_lengths) /
                     SUM(CASE WHEN l.avg_swolf IS NOT NULL THEN l.active_lengths ELSE 0 END) END
                AS avg_swolf,
           CASE WHEN SUM(l.active_lengths) > 0
                THEN SUM(l.stroke_count) * 1.0 / SUM(l.active_lengths) END
                AS avg_strokes_per_length,
           CASE WHEN SUM(CASE WHEN l.avg_hr IS NOT NULL THEN l.swim_time_s ELSE 0 END) > 0
                THEN SUM(l.avg_hr * l.swim_time_s) /
                     SUM(CASE WHEN l.avg_hr IS NOT NULL THEN l.swim_time_s ELSE 0 END) END
                AS avg_hr,
           MAX(l.max_hr) AS max_hr
    FROM swim_laps l
    JOIN activities a ON a.garmin_id = l.activity_id
    JOIN step_bounds b ON b.activity_id = l.activity_id
    WHERE substr(a.activity_date, 1, 10) BETWEEN ? AND ?
      AND l.distance_m > 0
      AND (b.step_count < 3
           OR l.workout_step_index IS NULL
           OR l.workout_step_index NOT IN (b.first_step, b.last_step))
    GROUP BY a.garmin_id, a.activity_date, a.name
    ORDER BY a.activity_date
"""
