from pathlib import Path

import pytest
from pydantic import ValidationError

from swimops.config import (
    athlete_profile_path,
    load_athlete_profile,
    update_athlete_profile,
)


def test_uses_configured_athlete_profile_path() -> None:
    assert athlete_profile_path({"SWIMOPS_ATHLETE_CONFIG": "/private/athlete.toml"}) == Path(
        "/private/athlete.toml"
    )


def test_loads_athlete_profile(tmp_path: Path) -> None:
    path = tmp_path / "athlete.toml"
    path.write_text(
        "pool_length_m = 25\n"
        "target_distance_m = 1500\n"
        "swim_days_per_week = 3\n"
        'available_equipment = ["fins", "pull_buoy"]\n'
    )

    profile = load_athlete_profile(path)

    assert profile.model_dump() == {
        "pool_length_m": 25,
        "target_distance_m": 1500,
        "swim_days_per_week": 3,
        "available_equipment": ["fins", "pull_buoy"],
    }


def test_rejects_invalid_athlete_profile(tmp_path: Path) -> None:
    path = tmp_path / "athlete.toml"
    path.write_text("swim_days_per_week = 8\n")

    with pytest.raises(ValidationError):
        load_athlete_profile(path)


def test_rejects_unsupported_equipment(tmp_path: Path) -> None:
    path = tmp_path / "athlete.toml"
    path.write_text('available_equipment = ["handplane"]\n')

    with pytest.raises(ValidationError):
        load_athlete_profile(path)


def test_updates_profile_without_discarding_existing_values(tmp_path: Path) -> None:
    path = tmp_path / "athlete.toml"
    path.write_text("pool_length_m = 25\ntarget_distance_m = 1500\n")

    profile = update_athlete_profile(
        path,
        swim_days_per_week=3,
        available_equipment=["fins", "kickboard"],
    )

    assert profile.model_dump() == {
        "pool_length_m": 25,
        "target_distance_m": 1500,
        "swim_days_per_week": 3,
        "available_equipment": ["fins", "kickboard"],
    }
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_athlete_profile(path) == profile
