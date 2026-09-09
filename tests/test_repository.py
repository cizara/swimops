from pathlib import Path

from swimops.repository import Activity, ActivityRepository


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
