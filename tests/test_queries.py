from pathlib import Path

import pytest

from swimops.queries import GarminHistory
from swimops.repository import Activity, ActivityRepository
from swimops.swimming import HrZone, ParsedSwim, SwimLap, SwimLength, SwimSession


def add_swim(repository: ActivityRepository, activity_id: int, activity_date: str) -> None:
    repository.register(
        Activity(activity_id, activity_date, "lap_swimming", f"Swim {activity_id}", Path("a.fit"))
    )
    session = SwimSession(
        activity_id, 25.0, 2, 2, 50.0, 65.0, 65.0, 50.0, 100.0, 130, 150, 20, 10.0, 35.0
    )
    lap = SwimLap(
        activity_id, 0, 1, 50.0, 50.0, 50.0, 50.0, 100.0, "freestyle", 20, 2, 130, 150, 35.0
    )
    length = SwimLength(activity_id, 0, "active", 25.0, 25.0, "freestyle", 10, 35.0)
    repository.replace_swim(
        ParsedSwim(session, (lap,), (length,), (HrZone(activity_id, 1, 40.0, 120),))
    )


@pytest.fixture
def history(tmp_path: Path) -> GarminHistory:
    database = tmp_path / "garmin.sqlite"
    with ActivityRepository(database) as repository:
        add_swim(repository, 1, "2026-09-09 10:00:00")
        add_swim(repository, 2, "2026-08-01 10:00:00")
        repository.register(Activity(3, "2026-09-08 10:00:00", "soccer", "Match", Path("b.fit")))
    return GarminHistory(database)


def test_lists_activities_with_filters(history: GarminHistory) -> None:
    activities = history.list_activities(
        sport="lap_swimming", from_date="2026-09-01", to_date="2026-09-30"
    )

    assert [activity["activity_id"] for activity in activities] == [1]
    assert activities[0]["avg_swolf"] == 35.0


def test_gets_activity_and_full_swim_session(history: GarminHistory) -> None:
    activity = history.get_activity(1)
    session = history.get_swim_session(1, include_lengths=True)

    assert activity["swim"]["zones_s"] == {"z1": 40.0}
    assert session["laps"][0]["pace_100m_s"] == 100.0
    assert session["lengths"][0]["swolf"] == 35.0


def test_gets_compact_swim_history_in_reverse_date_order(history: GarminHistory) -> None:
    result = history.get_swim_history("2026-01-01", "2026-12-31")

    assert [activity["activity_id"] for activity in result] == [1, 2]
    assert result[0]["zones_s"] == {"z1": 40.0}


def test_rejects_unknown_or_non_swim_activity(history: GarminHistory) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        history.get_activity(999)
    with pytest.raises(ValueError, match="not a processed pool session"):
        history.get_swim_session(3)


def test_rejects_inverted_activity_range(history: GarminHistory) -> None:
    with pytest.raises(ValueError, match="from_date"):
        history.list_activities(from_date="2026-09-02", to_date="2026-09-01")
