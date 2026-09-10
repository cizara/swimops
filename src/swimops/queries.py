from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any


class GarminHistory:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def list_activities(
        self,
        sport: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        _validate_limit(limit)
        clauses: list[str] = []
        parameters: list[Any] = []
        start = _validate_date(from_date) if from_date else None
        end = _validate_date(to_date) if to_date else None
        if start and end and start > end:
            raise ValueError("from_date no puede ser posterior a to_date.")
        if sport:
            clauses.append("a.sport = ?")
            parameters.append(sport)
        if start:
            clauses.append("substr(a.activity_date, 1, 10) >= ?")
            parameters.append(start)
        if end:
            clauses.append("substr(a.activity_date, 1, 10) <= ?")
            parameters.append(end)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT a.garmin_id, a.activity_date, a.sport, a.name,
                       s.distance_m, s.swim_time_s, s.avg_pace_100m,
                       s.avg_swolf, s.avg_hr, s.max_hr
                FROM activities a
                LEFT JOIN swim_sessions s ON s.activity_id = a.garmin_id
                {where}
                ORDER BY a.activity_date DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [_activity_summary(row) for row in rows]

    def get_activity(self, activity_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT a.garmin_id, a.activity_date, a.sport, a.name,
                       s.distance_m, s.swim_time_s, s.avg_pace_100m,
                       s.avg_swolf, s.avg_hr, s.max_hr,
                       s.pool_length_m, s.elapsed_time_s, s.timer_time_s,
                       s.total_lengths, s.active_lengths, s.total_strokes,
                       s.avg_strokes_per_length
                FROM activities a
                LEFT JOIN swim_sessions s ON s.activity_id = a.garmin_id
                WHERE a.garmin_id = ?
                """,
                (activity_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"No existe la actividad {activity_id}.")
            result = _activity_summary(row)
            if row[4] is not None:
                result["swim"] = {
                    "pool_length_m": row[10],
                    "elapsed_time_s": row[11],
                    "timer_time_s": row[12],
                    "total_lengths": row[13],
                    "active_lengths": row[14],
                    "total_strokes": row[15],
                    "avg_strokes_per_length": row[16],
                    "zones_s": self._zones(connection, activity_id),
                }
        return result

    def get_swim_history(
        self, from_date: str, to_date: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        start = _validate_date(from_date)
        end = _validate_date(to_date)
        if start > end:
            raise ValueError("from_date no puede ser posterior a to_date.")
        _validate_limit(limit)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.garmin_id, a.activity_date, a.name,
                       s.distance_m, s.elapsed_time_s, s.timer_time_s,
                       s.swim_time_s, s.avg_pace_100m, s.avg_swolf,
                       s.avg_strokes_per_length, s.avg_hr, s.max_hr
                FROM swim_sessions s
                JOIN activities a ON a.garmin_id = s.activity_id
                WHERE substr(a.activity_date, 1, 10) BETWEEN ? AND ?
                ORDER BY a.activity_date DESC
                LIMIT ?
                """,
                (start, end, limit),
            ).fetchall()
            return [
                {
                    "activity_id": row[0],
                    "date": row[1],
                    "name": row[2],
                    "distance_m": row[3],
                    "elapsed_time_s": row[4],
                    "timer_time_s": row[5],
                    "swim_time_s": row[6],
                    "avg_pace_100m_s": row[7],
                    "avg_swolf": row[8],
                    "avg_strokes_per_length": row[9],
                    "avg_hr": row[10],
                    "max_hr": row[11],
                    "zones_s": self._zones(connection, row[0]),
                }
                for row in rows
            ]

    def get_swim_session(
        self, activity_id: int, include_lengths: bool = False
    ) -> dict[str, Any]:
        activity = self.get_activity(activity_id)
        if "swim" not in activity:
            raise ValueError(f"La actividad {activity_id} no es una sesión de piscina procesada.")
        with self._connect() as connection:
            laps = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT lap_index, workout_step_index, distance_m,
                           elapsed_time_s, timer_time_s, swim_time_s,
                           pace_100m AS pace_100m_s, stroke_type,
                           stroke_count, active_lengths, avg_hr, max_hr, avg_swolf
                    FROM swim_laps
                    WHERE activity_id = ? ORDER BY lap_index
                    """,
                    (activity_id,),
                )
            ]
            result = {"summary": activity, "laps": laps}
            if include_lengths:
                result["lengths"] = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT length_index, length_type, distance_m, duration_s,
                               stroke_type, stroke_count, swolf
                        FROM swim_lengths
                        WHERE activity_id = ? ORDER BY length_index
                        """,
                        (activity_id,),
                    )
                ]
        return result

    def get_sync_status(self) -> dict[str, Any]:
        with self._connect() as connection:
            activity = connection.execute(
                """
                SELECT COUNT(*), MIN(substr(activity_date, 1, 10)),
                       MAX(substr(activity_date, 1, 10))
                FROM activities
                """
            ).fetchone()
            parsed_swims = connection.execute(
                "SELECT COUNT(*) FROM swim_sessions"
            ).fetchone()[0]
            has_sync_runs = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sync_runs'"
            ).fetchone()
            latest = None
            if has_sync_runs:
                row = connection.execute(
                    """
                    SELECT finished_at, since_date, until_date,
                           downloaded, existing, failed
                    FROM sync_runs ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
                if row:
                    latest = dict(row)
        return {
            "activity_count": activity[0],
            "from_date": activity[1],
            "to_date": activity[2],
            "parsed_swim_count": parsed_swims,
            "last_sync": latest,
        }

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise FileNotFoundError(f"No existe la base de datos: {self.database_path}")
        connection = sqlite3.connect(f"{self.database_path.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _zones(connection: sqlite3.Connection, activity_id: int) -> dict[str, float]:
        return {
            f"z{row['zone']}": row["seconds"]
            for row in connection.execute(
                "SELECT zone, seconds FROM hr_zones WHERE activity_id = ? ORDER BY zone",
                (activity_id,),
            )
        }


def _activity_summary(row: sqlite3.Row) -> dict[str, Any]:
    result: dict[str, Any] = {
        "activity_id": row[0],
        "date": row[1],
        "sport": row[2],
        "name": row[3],
    }
    if row[4] is not None:
        result.update(
            distance_m=row[4],
            swim_time_s=row[5],
            avg_pace_100m_s=row[6],
            avg_swolf=row[7],
            avg_hr=row[8],
            max_hr=row[9],
        )
    return result


def _validate_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Las fechas deben tener formato YYYY-MM-DD.") from error
    if parsed.isoformat() != value:
        raise ValueError("Las fechas deben tener formato YYYY-MM-DD.")
    return value


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 500:
        raise ValueError("limit debe estar entre 1 y 500.")
