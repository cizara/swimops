from pathlib import Path

import pytest

from swimops.reports import SwimReports, routine_key, summarize_sessions
from swimops.repository import Activity, ActivityRepository
from swimops.swimming import ParsedSwim, SwimLap, SwimSession


def lap(activity_id: int, index: int, step: int, distance: float, seconds: float) -> SwimLap:
    return SwimLap(
        activity_id, index, step, distance, seconds, seconds, seconds,
        seconds * 100 / distance, "freestyle", int(distance / 2.5),
        int(distance / 25), 130 + index, 150 + index, 35.0 + index,
    )


def add_session(
    repository: ActivityRepository, activity_id: int, name: str, activity_date: str
) -> None:
    laps = (
        lap(activity_id, 0, 0, 100, 120),
        lap(activity_id, 1, 2, 200, 200),
        lap(activity_id, 2, 4, 300, 330),
        lap(activity_id, 3, 6, 100, 140),
    )
    session = SwimSession(
        activity_id, 25, 28, 28, 700, 790, 790, 790, 112.86,
        132, 153, 280, 10, 36,
    )
    repository.register(
        Activity(activity_id, activity_date, "lap_swimming", name, Path("swim.fit"))
    )
    repository.replace_swim(ParsedSwim(session, laps, (), ()))


@pytest.fixture
def reports(tmp_path: Path) -> SwimReports:
    database = tmp_path / "garmin.sqlite"
    with ActivityRepository(database) as repository:
        add_session(repository, 1, "Cafe A: Technique", "2026-09-01 10:00:00")
        add_session(repository, 2, "Café A: Technique", "2026-09-08 10:00:00")
        add_session(repository, 3, "Day B: Power", "2026-09-09 10:00:00")
        repository.register(
            Activity(
                4,
                "2026-09-07 18:00:00",
                "soccer",
                "Match",
                Path("soccer.fit"),
                4200,
                3600,
            )
        )
    return SwimReports(database)


def test_groups_routine_names_without_accents(reports: SwimReports) -> None:
    routines = reports.list_routines()

    assert [(item["key"], item["sessions"]) for item in routines] == [
        ("day b", 1),
        ("cafe a", 2),
    ]
    assert routine_key("  CAFÉ   A: another set") == "cafe a"


def test_filters_sessions_by_routine(reports: SwimReports) -> None:
    sessions = reports.sessions("2026-09-01", "2026-09-30", ["cafe a"])

    assert [session["activity_id"] for session in sessions] == [1, 2]
    assert sessions[0]["distance_m"] == 700


def test_lists_all_sports_for_general_reports(
    reports: SwimReports,
) -> None:
    activities = reports.activities("2026-09-01", "2026-09-30")

    assert len(activities) == 4
    assert {activity["sport"] for activity in activities} == {
        "lap_swimming",
        "soccer",
    }
    soccer = next(activity for activity in activities if activity["sport"] == "soccer")
    assert soccer["distance_m"] == 4200
    assert soccer["duration_s"] == 3600


def test_excludes_first_and_last_workout_blocks(reports: SwimReports) -> None:
    sessions = reports.sessions("2026-09-01", "2026-09-30", ["day b"], main_only=True)

    assert len(sessions) == 1
    assert sessions[0]["distance_m"] == 500
    assert sessions[0]["swim_time_s"] == 530
    assert sessions[0]["avg_pace_100m_s"] == 106


def test_rejects_inverted_range(reports: SwimReports) -> None:
    with pytest.raises(ValueError, match="from_date"):
        reports.sessions("2026-09-02", "2026-09-01")


def test_summarizes_sessions_with_weighted_metrics(reports: SwimReports) -> None:
    sessions = reports.sessions("2026-09-01", "2026-09-30", ["cafe a"])
    summary = summarize_sessions(sessions)

    assert summary["sessions"] == 2
    assert summary["distance_m"] == 1400
    assert summary["avg_pace_100m_s"] == pytest.approx(790 / 7)
