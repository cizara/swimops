from __future__ import annotations

import json
import os
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from swimops.workouts import Equipment


class AthleteProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pool_length_m: PositiveInt | None = None
    target_distance_m: PositiveInt | None = None
    swim_days_per_week: int | None = Field(default=None, ge=1, le=7)
    available_equipment: list[Equipment] | None = None


def athlete_profile_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get("SWIMOPS_ATHLETE_CONFIG", "athlete.toml")).expanduser()


def load_athlete_profile(path: Path | None = None) -> AthleteProfile:
    profile_path = path or athlete_profile_path()
    with profile_path.open("rb") as profile_file:
        return AthleteProfile.model_validate(tomllib.load(profile_file))


def update_athlete_profile(
    path: Path,
    *,
    pool_length_m: int | None = None,
    target_distance_m: int | None = None,
    swim_days_per_week: int | None = None,
    available_equipment: list[str] | None = None,
) -> AthleteProfile:
    current = load_athlete_profile(path).model_dump() if path.is_file() else {}
    updates = {
        key: value
        for key, value in {
            "pool_length_m": pool_length_m,
            "target_distance_m": target_distance_m,
            "swim_days_per_week": swim_days_per_week,
            "available_equipment": available_equipment,
        }.items()
        if value is not None
    }
    profile = AthleteProfile.model_validate({**current, **updates})
    _write_athlete_profile(path, profile)
    return profile


def _write_athlete_profile(path: Path, profile: AthleteProfile) -> None:
    data = profile.model_dump(exclude_none=True)
    lines = []
    if "pool_length_m" in data:
        lines.append(f"pool_length_m = {data['pool_length_m']}")
    if "target_distance_m" in data:
        lines.append(f"target_distance_m = {data['target_distance_m']}")
    if "swim_days_per_week" in data:
        lines.append(f"swim_days_per_week = {data['swim_days_per_week']}")
    if "available_equipment" in data:
        equipment = ", ".join(json.dumps(item) for item in data["available_equipment"])
        lines.append(f"available_equipment = [{equipment}]")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write("\n".join(lines) + "\n")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
