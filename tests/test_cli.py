from datetime import date
from pathlib import Path

import pytest

from swimops import cli
from swimops.cli import build_parser, iso_date, positive_int
from swimops.processing import ParseSummary
from swimops.sync import SyncSummary


def test_activities_defaults_to_ten() -> None:
    args = build_parser().parse_args(["activities"])
    assert args.limit == 10


def test_limit_must_be_positive() -> None:
    with pytest.raises(Exception):
        positive_int("0")


def test_sync_arguments() -> None:
    args = build_parser().parse_args(
        [
            "sync",
            "--since",
            "2026-04-15",
            "--until",
            "2026-09-09",
            "--data-dir",
            "/tmp/garmin-data",
        ]
    )

    assert args.since == date(2026, 4, 15)
    assert args.until == date(2026, 9, 9)
    assert args.data_dir == Path("/tmp/garmin-data")


def test_iso_date_requires_extended_format() -> None:
    with pytest.raises(Exception):
        iso_date("20260909")


def test_sync_prints_summary_and_fails_if_an_activity_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = object()
    monkeypatch.setattr(cli, "load_session", lambda: client)

    def run_sync(
        received_client: object,
        since: date,
        until: date,
        data_dir: Path,
    ) -> SyncSummary:
        assert received_client is client
        assert (since, until) == (date(2026, 4, 15), date(2026, 9, 9))
        assert data_dir == Path("data")
        return SyncSummary(downloaded=2, existing=3, failed=1)

    monkeypatch.setattr(cli, "sync_activities", run_sync)
    monkeypatch.setattr(
        cli,
        "parse_swims",
        lambda data_dir: ParseSummary(parsed=2, existing=3),
    )

    result = cli.main(
        ["sync", "--since", "2026-04-15", "--until", "2026-09-09"]
    )

    assert result == 1
    assert capsys.readouterr().out == (
        "Downloaded: 2 | Existing: 3 | Failed: 1\n"
        "Swims processed: 2 | Existing: 3 | Failed: 0\n"
    )


def test_parse_swims_does_not_load_garmin_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "load_session", lambda: pytest.fail("unexpected login"))
    monkeypatch.setattr(
        cli,
        "parse_swims",
        lambda data_dir, force: ParseSummary(parsed=28),
    )

    assert cli.main(["parse-swims"]) == 0
    assert capsys.readouterr().out == "Processed: 28 | Existing: 0 | Failed: 0\n"


def test_workout_preview_does_not_load_garmin_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "workout.json"
    path.write_text(
        '{"name":"Technique","pool_length_m":25,'
        '"steps":[{"type":"swim","distance_m":100,"drill":"drill"}]}'
    )
    monkeypatch.setattr(cli, "load_session", lambda: pytest.fail("unexpected login"))

    assert cli.main(["workout-preview", str(path)]) == 0
    assert "Total distance: 100 m" in capsys.readouterr().out


def test_workouts_lists_remote_workouts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = object()
    monkeypatch.setattr(cli, "load_session", lambda: client)
    monkeypatch.setattr(
        cli,
        "list_garmin_workouts",
        lambda received, limit: [
            {
                "workout_id": 123,
                "name": "Day A",
                "sport": "swimming",
                "distance_m": 1500,
                "duration_s": 0,
                "pool_length_m": 25,
                "updated_at": None,
            }
        ],
    )

    assert cli.main(["workouts", "--limit", "5"]) == 0
    assert "123\tswimming\t1500\t25\tDay A" in capsys.readouterr().out


def test_workout_create_requires_confirmation_before_login(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "workout.json"
    path.write_text(
        '{"name":"Easy","pool_length_m":25,'
        '"steps":[{"type":"swim","distance_m":500}]}'
    )
    monkeypatch.setattr(cli, "load_session", lambda: pytest.fail("unexpected login"))

    assert cli.main(["workout-create", str(path)]) == 1
    assert "use --confirm" in capsys.readouterr().err


def test_workout_create_uploads_confirmed_workout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "workout.json"
    path.write_text(
        '{"name":"Easy","pool_length_m":25,'
        '"steps":[{"type":"swim","distance_m":500}]}'
    )
    client = object()
    monkeypatch.setattr(cli, "load_session", lambda: client)
    monkeypatch.setattr(
        cli,
        "create_garmin_swim_workout",
        lambda received, workout: {
            "workout_id": 456,
            "name": workout.name,
            "sport": "swimming",
            "distance_m": 500,
            "pool_length_m": 25,
        },
    )

    assert cli.main(["workout-create", str(path), "--confirm"]) == 0
    assert '"workout_id": 456' in capsys.readouterr().out
