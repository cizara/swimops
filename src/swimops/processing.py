from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from swimops.repository import ActivityRepository
from swimops.swimming import parse_swim_fit


@dataclass(frozen=True, slots=True)
class ParseSummary:
    parsed: int = 0
    existing: int = 0
    failed: int = 0


def parse_swims(data_dir: Path, force: bool = False) -> ParseSummary:
    parsed = existing = failed = 0
    with ActivityRepository(Path(data_dir) / "garmin.sqlite") as repository:
        for activity in repository.list_activities("lap_swimming"):
            if not force and repository.is_swim_parsed(activity.garmin_id):
                existing += 1
                continue
            try:
                swim = parse_swim_fit(activity.fit_path, activity.garmin_id)
                repository.replace_swim(swim)
                parsed += 1
            except Exception as error:
                failed += 1
                print(f"Activity {activity.garmin_id}: {error}", file=sys.stderr)
    return ParseSummary(parsed=parsed, existing=existing, failed=failed)
