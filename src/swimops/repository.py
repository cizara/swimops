"""Persistencia local de actividades descargadas de Garmin."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Activity:
    """Datos mínimos que se conservan para una actividad descargada."""

    garmin_id: int
    date: str
    sport: str
    name: str
    fit_path: Path


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

    def register(self, activity: Activity) -> bool:
        """Registra una actividad y devuelve ``False`` si ya existía.

        La inserción es atómica: un fallo no deja un registro parcial y permite
        que una sincronización posterior vuelva a intentar esa actividad.
        """
        with self._connection:
            result = self._connection.execute(
                """
                INSERT OR IGNORE INTO activities
                    (garmin_id, activity_date, sport, name, fit_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    activity.garmin_id,
                    activity.date,
                    activity.sport,
                    activity.name,
                    str(activity.fit_path),
                ),
            )
        return result.rowcount == 1

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
