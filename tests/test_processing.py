from pathlib import Path

import pytest

from swimops import processing
from swimops.processing import ParseSummary, parse_swims
from swimops.repository import Activity, ActivityRepository
from swimops.swimming import ParsedSwim, SwimSession


def test_parses_pending_swims_and_skips_them_next_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fit_path = tmp_path / "fit/2026/09/123.fit"
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        repository.register(Activity(123, "2026-09-09", "lap_swimming", "Pool", fit_path))

    parsed = ParsedSwim(
        SwimSession(123, 25.0, 1, 1, 25.0, 25.0, 25.0, 25.0, 100.0, 130, 150, 10, 10.0, 35.0),
        (),
        (),
        (),
    )
    calls: list[tuple[Path, int]] = []

    def parse(path: Path, activity_id: int) -> ParsedSwim:
        calls.append((path, activity_id))
        return parsed

    monkeypatch.setattr(processing, "parse_swim_fit", parse)

    assert parse_swims(tmp_path) == ParseSummary(parsed=1)
    assert parse_swims(tmp_path) == ParseSummary(existing=1)
    assert calls == [(fit_path, 123)]
