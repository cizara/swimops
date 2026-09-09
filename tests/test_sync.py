from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest
from garminconnect import Garmin

from swimops.download import fit_path
from swimops.repository import Activity, ActivityRepository
from swimops.sync import SyncSummary, sync_activities


def original_with_fit(contents: bytes = b"FIT bytes") -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("activity.fit", contents)
    return result.getvalue()


def api_activity(activity_id: int, timestamp: str = "2026-09-09 10:00:00") -> dict:
    return {
        "activityId": activity_id,
        "startTimeLocal": timestamp,
        "activityType": {"typeKey": "lap_swimming"},
        "activityName": f"Activity {activity_id}",
    }


class Client:
    def __init__(self, activities: list[dict], failures: set[int] | None = None) -> None:
        self.activities = activities
        self.failures = failures or set()
        self.queries: list[tuple[str, str | None]] = []
        self.downloads: list[int] = []

    def get_activities_by_date(
        self, startdate: str, enddate: str | None = None
    ) -> list[dict]:
        self.queries.append((startdate, enddate))
        return self.activities

    def download_activity(
        self, activity_id: str, dl_fmt: Garmin.ActivityDownloadFormat
    ) -> bytes:
        identifier = int(activity_id)
        self.downloads.append(identifier)
        if identifier in self.failures:
            raise RuntimeError("download failed")
        return original_with_fit(str(identifier).encode())


def test_sync_downloads_all_activities_in_inclusive_range(tmp_path: Path) -> None:
    client = Client(
        [
            api_activity(1, "2026-04-15 00:00:00"),
            api_activity(2, "2026-09-09 23:59:59"),
        ]
    )

    summary = sync_activities(
        client, date(2026, 4, 15), date(2026, 9, 9), tmp_path
    )

    assert summary == SyncSummary(downloaded=2)
    assert client.queries == [("2026-04-15", "2026-09-09")]
    assert client.downloads == [1, 2]
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        assert repository.is_registered(1)
        assert repository.is_registered(2)


def test_sync_skips_complete_activity(tmp_path: Path) -> None:
    activity_date = date(2026, 9, 9)
    destination = fit_path(tmp_path, 1, activity_date)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"existing")
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        repository.register(
            Activity(1, "2026-09-09 10:00:00", "swimming", "Existing", destination)
        )
    client = Client([api_activity(1)])

    summary = sync_activities(client, activity_date, activity_date, tmp_path)

    assert summary == SyncSummary(existing=1)
    assert client.downloads == []


def test_sync_registers_existing_fit_without_downloading(tmp_path: Path) -> None:
    activity_date = date(2026, 9, 9)
    destination = fit_path(tmp_path, 1, activity_date)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"existing")
    client = Client([api_activity(1)])

    summary = sync_activities(client, activity_date, activity_date, tmp_path)

    assert summary == SyncSummary(existing=1)
    assert client.downloads == []
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        assert repository.is_registered(1)


def test_sync_downloads_missing_fit_for_registered_activity(tmp_path: Path) -> None:
    activity_date = date(2026, 9, 9)
    destination = fit_path(tmp_path, 1, activity_date)
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        repository.register(
            Activity(1, "2026-09-09 10:00:00", "swimming", "Missing", destination)
        )
    client = Client([api_activity(1)])

    summary = sync_activities(client, activity_date, activity_date, tmp_path)

    assert summary == SyncSummary(downloaded=1)
    assert destination.read_bytes() == b"1"


def test_sync_continues_after_failure_and_does_not_register_it(
    tmp_path: Path,
) -> None:
    client = Client([api_activity(1), api_activity(2)], failures={1})
    activity_date = date(2026, 9, 9)

    summary = sync_activities(client, activity_date, activity_date, tmp_path)

    assert summary == SyncSummary(downloaded=1, failed=1)
    assert client.downloads == [1, 2]
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        assert not repository.is_registered(1)
        assert repository.is_registered(2)


def test_sync_repairs_registration_failure_without_redownloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    activity_date = date(2026, 9, 9)
    original_register = ActivityRepository.register

    def fail_registration(self: ActivityRepository, activity: Activity) -> bool:
        raise RuntimeError("database failed")

    monkeypatch.setattr(ActivityRepository, "register", fail_registration)
    first_client = Client([api_activity(1)])

    first_summary = sync_activities(
        first_client, activity_date, activity_date, tmp_path
    )

    assert first_summary == SyncSummary(failed=1)
    assert fit_path(tmp_path, 1, activity_date).is_file()

    monkeypatch.setattr(ActivityRepository, "register", original_register)
    retry_client = Client([api_activity(1)])
    retry_summary = sync_activities(
        retry_client, activity_date, activity_date, tmp_path
    )

    assert retry_summary == SyncSummary(existing=1)
    assert retry_client.downloads == []
    with ActivityRepository(tmp_path / "garmin.sqlite") as repository:
        assert repository.is_registered(1)


def test_sync_counts_invalid_activity_and_continues(tmp_path: Path) -> None:
    client = Client([{"activityName": "Invalid"}, api_activity(2)])
    activity_date = date(2026, 9, 9)

    summary = sync_activities(client, activity_date, activity_date, tmp_path)

    assert summary == SyncSummary(downloaded=1, failed=1)
    assert client.downloads == [2]


def test_sync_rejects_inverted_range_without_querying(tmp_path: Path) -> None:
    client = Client([])

    try:
        sync_activities(client, date(2026, 9, 10), date(2026, 9, 9), tmp_path)
    except ValueError as error:
        assert "--since" in str(error)
    else:
        raise AssertionError("expected ValueError")

    assert client.queries == []


def test_garminconnect_date_query_paginates_until_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Garmin()
    starts: list[str] = []

    def connectapi(url: str, params: dict[str, str]) -> list[dict]:
        starts.append(params["start"])
        if params["start"] == "0":
            return [api_activity(identifier) for identifier in range(1, 21)]
        if params["start"] == "20":
            return [api_activity(identifier) for identifier in range(21, 26)]
        return []

    monkeypatch.setattr(client, "connectapi", connectapi)

    activities = client.get_activities_by_date("2026-04-15", "2026-09-09")

    assert len(activities) == 25
    assert starts == ["0", "20", "40"]
