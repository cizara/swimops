from pathlib import Path

from swimops.repository import Activity, ActivityRepository
from swimops.swimming import HrZone, ParsedSwim, SwimLap, SwimLength, SwimSession


def activity(garmin_id: int = 123) -> Activity:
    return Activity(
        garmin_id=garmin_id,
        date="2026-09-08 18:30:00",
        sport="lap_swimming",
        name="Series",
        fit_path=Path("fits/2026/09/123.fit"),
    )


def test_creates_schema_at_configured_path(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "activities.sqlite3"

    with ActivityRepository(database_path) as repository:
        assert database_path.is_file()
        assert repository.is_registered(123) is False


def test_registers_activity_and_detects_duplicate(tmp_path: Path) -> None:
    database_path = tmp_path / "activities.sqlite3"

    with ActivityRepository(database_path) as repository:
        assert repository.register(activity()) is True
        assert repository.is_registered(123) is True
        assert repository.register(activity()) is False


def test_registration_survives_reopening_database(tmp_path: Path) -> None:
    database_path = tmp_path / "activities.sqlite3"

    with ActivityRepository(database_path) as repository:
        assert repository.register(activity()) is True

    with ActivityRepository(database_path) as repository:
        assert repository.is_registered(123) is True
        assert repository.register(activity()) is False


def test_replaces_all_derived_swim_data_atomically(tmp_path: Path) -> None:
    database_path = tmp_path / "activities.sqlite3"
    session = SwimSession(123, 25.0, 2, 1, 25.0, 35.0, 35.0, 25.0, 100.0, 130, 150, 10, 10.0, 35.0)
    lap = SwimLap(123, 0, 2, 25.0, 25.0, 25.0, 25.0, 100.0, "freestyle", 10, 1, 130, 150, 35.0)
    length = SwimLength(123, 0, "active", 25.0, 25.0, "freestyle", 10, 35.0)
    swim = ParsedSwim(session, (lap,), (length,), (HrZone(123, 1, 20.0, 120),))

    with ActivityRepository(database_path) as repository:
        repository.register(activity())
        repository.replace_swim(swim)
        repository.replace_swim(swim)

        assert repository.is_swim_parsed(123)
        assert repository._connection.execute("SELECT COUNT(*) FROM swim_laps").fetchone() == (1,)
        assert repository._connection.execute("SELECT COUNT(*) FROM swim_lengths").fetchone() == (1,)
        assert repository._connection.execute("SELECT COUNT(*) FROM hr_zones").fetchone() == (1,)
