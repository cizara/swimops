"""Persistencia local de actividades descargadas de Garmin."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from swimops.swimming import ParsedSwim


@dataclass(frozen=True, slots=True)
class Activity:
    """Datos mínimos que se conservan para una actividad descargada."""

    garmin_id: int
    date: str
    sport: str
    name: str
    fit_path: Path
    distance_m: float | None = None
    duration_s: float | None = None


class ActivityRepository:
    """Registro SQLite de actividades, con una transacción por actividad."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> ActivityRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def is_registered(self, garmin_id: int) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM activities WHERE garmin_id = ?", (garmin_id,)
        ).fetchone()
        return row is not None

    def list_activities(self, sport: str | None = None) -> list[Activity]:
        query = "SELECT garmin_id, activity_date, sport, name, fit_path FROM activities"
        parameters: tuple[str, ...] = ()
        if sport is not None:
            query += " WHERE sport = ?"
            parameters = (sport,)
        query += " ORDER BY activity_date"
        return [
            Activity(row[0], row[1], row[2], row[3], Path(row[4]))
            for row in self._connection.execute(query, parameters)
        ]

    def is_swim_parsed(self, activity_id: int) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM swim_sessions WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        return row is not None

    def register(self, activity: Activity) -> bool:
        """Registra una actividad y devuelve ``False`` si ya existía.

        La inserción es atómica: un fallo no deja un registro parcial y permite
        que una sincronización posterior vuelva a intentar esa actividad.
        """
        exists = self.is_registered(activity.garmin_id)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO activities
                    (garmin_id, activity_date, sport, name, fit_path, distance_m, duration_s)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(garmin_id) DO UPDATE SET
                    activity_date = excluded.activity_date,
                    sport = excluded.sport,
                    name = excluded.name,
                    fit_path = excluded.fit_path,
                    distance_m = COALESCE(excluded.distance_m, activities.distance_m),
                    duration_s = COALESCE(excluded.duration_s, activities.duration_s)
                """,
                (
                    activity.garmin_id,
                    activity.date,
                    activity.sport,
                    activity.name,
                    str(activity.fit_path),
                    activity.distance_m,
                    activity.duration_s,
                ),
            )
        return not exists

    def record_sync(
        self,
        since: date,
        until: date,
        downloaded: int,
        existing: int,
        failed: int,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO sync_runs
                    (finished_at, since_date, until_date, downloaded, existing, failed)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    since.isoformat(),
                    until.isoformat(),
                    downloaded,
                    existing,
                    failed,
                ),
            )

    def replace_swim(self, swim: ParsedSwim) -> None:
        activity_id = swim.session.activity_id
        with self._connection:
            for table in ("hr_zones", "swim_lengths", "swim_laps", "swim_sessions"):
                self._connection.execute(
                    f"DELETE FROM {table} WHERE activity_id = ?", (activity_id,)
                )
            session = swim.session
            self._connection.execute(
                """
                INSERT INTO swim_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.activity_id,
                    session.pool_length_m,
                    session.total_lengths,
                    session.active_lengths,
                    session.distance_m,
                    session.elapsed_time_s,
                    session.timer_time_s,
                    session.swim_time_s,
                    session.avg_pace_100m,
                    session.avg_hr,
                    session.max_hr,
                    session.total_strokes,
                    session.avg_strokes_per_length,
                    session.avg_swolf,
                ),
            )
            self._connection.executemany(
                "INSERT INTO swim_laps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        lap.activity_id,
                        lap.lap_index,
                        lap.workout_step_index,
                        lap.distance_m,
                        lap.elapsed_time_s,
                        lap.timer_time_s,
                        lap.swim_time_s,
                        lap.pace_100m,
                        lap.stroke_type,
                        lap.stroke_count,
                        lap.active_lengths,
                        lap.avg_hr,
                        lap.max_hr,
                        lap.avg_swolf,
                    )
                    for lap in swim.laps
                ],
            )
            self._connection.executemany(
                "INSERT INTO swim_lengths VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        length.activity_id,
                        length.length_index,
                        length.length_type,
                        length.distance_m,
                        length.duration_s,
                        length.stroke_type,
                        length.stroke_count,
                        length.swolf,
                    )
                    for length in swim.lengths
                ],
            )
            self._connection.executemany(
                "INSERT INTO hr_zones VALUES (?, ?, ?, ?)",
                [
                    (zone.activity_id, zone.zone, zone.seconds, zone.high_boundary_bpm)
                    for zone in swim.hr_zones
                ],
            )

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    garmin_id INTEGER PRIMARY KEY,
                    activity_date TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    name TEXT NOT NULL,
                    fit_path TEXT NOT NULL
                )
                """
            )
            columns = {
                row[1]
                for row in self._connection.execute("PRAGMA table_info(activities)")
            }
            if "distance_m" not in columns:
                self._connection.execute("ALTER TABLE activities ADD COLUMN distance_m REAL")
            if "duration_s" not in columns:
                self._connection.execute("ALTER TABLE activities ADD COLUMN duration_s REAL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS swim_sessions (
                    activity_id INTEGER PRIMARY KEY,
                    pool_length_m REAL NOT NULL,
                    total_lengths INTEGER NOT NULL,
                    active_lengths INTEGER NOT NULL,
                    distance_m REAL NOT NULL,
                    elapsed_time_s REAL NOT NULL,
                    timer_time_s REAL NOT NULL,
                    swim_time_s REAL NOT NULL,
                    avg_pace_100m REAL,
                    avg_hr INTEGER,
                    max_hr INTEGER,
                    total_strokes INTEGER NOT NULL,
                    avg_strokes_per_length REAL,
                    avg_swolf REAL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS swim_laps (
                    activity_id INTEGER NOT NULL,
                    lap_index INTEGER NOT NULL,
                    workout_step_index INTEGER,
                    distance_m REAL NOT NULL,
                    elapsed_time_s REAL NOT NULL,
                    timer_time_s REAL NOT NULL,
                    swim_time_s REAL NOT NULL,
                    pace_100m REAL,
                    stroke_type TEXT,
                    stroke_count INTEGER NOT NULL,
                    active_lengths INTEGER NOT NULL,
                    avg_hr INTEGER,
                    max_hr INTEGER,
                    avg_swolf REAL,
                    PRIMARY KEY (activity_id, lap_index)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS swim_lengths (
                    activity_id INTEGER NOT NULL,
                    length_index INTEGER NOT NULL,
                    length_type TEXT NOT NULL,
                    distance_m REAL NOT NULL,
                    duration_s REAL NOT NULL,
                    stroke_type TEXT,
                    stroke_count INTEGER,
                    swolf REAL,
                    PRIMARY KEY (activity_id, length_index)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS hr_zones (
                    activity_id INTEGER NOT NULL,
                    zone INTEGER NOT NULL,
                    seconds REAL NOT NULL,
                    high_boundary_bpm INTEGER,
                    PRIMARY KEY (activity_id, zone)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY,
                    finished_at TEXT NOT NULL,
                    since_date TEXT NOT NULL,
                    until_date TEXT NOT NULL,
                    downloaded INTEGER NOT NULL,
                    existing INTEGER NOT NULL,
                    failed INTEGER NOT NULL
                )
                """
            )
