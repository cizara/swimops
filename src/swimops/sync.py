from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from garminconnect import GarminConnectAuthenticationError

from swimops.download import GarminDownloadClient, download_fit, fit_path
from swimops.repository import Activity, ActivityRepository


class GarminSyncClient(GarminDownloadClient, Protocol):
    def get_activities_by_date(
        self, startdate: str, enddate: str | None = None
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class SyncSummary:
    downloaded: int = 0
    existing: int = 0
    failed: int = 0


def sync_activities(
    client: GarminSyncClient, since: date, until: date, data_dir: Path
) -> SyncSummary:
    if since > until:
        raise ValueError("--since no puede ser posterior a --until.")

    activities = client.get_activities_by_date(since.isoformat(), until.isoformat())
    downloaded = existing = failed = 0

    with ActivityRepository(Path(data_dir) / "garmin.sqlite") as repository:
        for raw_activity in activities:
            activity_id: Any = "desconocida"
            try:
                activity_id = raw_activity.get("activityId", activity_id)
                activity, activity_date = _activity_from_api(raw_activity, data_dir)
                destination = fit_path(data_dir, activity.garmin_id, activity_date)
                registered = repository.is_registered(activity.garmin_id)

                if registered and destination.is_file():
                    existing += 1
                    continue

                if destination.is_file():
                    repository.register(activity)
                    existing += 1
                    continue

                downloaded_path = download_fit(
                    client, activity.garmin_id, activity_date, data_dir
                )
                repository.register(
                    Activity(
                        garmin_id=activity.garmin_id,
                        date=activity.date,
                        sport=activity.sport,
                        name=activity.name,
                        fit_path=downloaded_path,
                    )
                )
                downloaded += 1
            except GarminConnectAuthenticationError:
                raise
            except Exception as error:
                failed += 1
                print(f"Actividad {activity_id}: {error}", file=sys.stderr)

        repository.record_sync(since, until, downloaded, existing, failed)

    return SyncSummary(downloaded=downloaded, existing=existing, failed=failed)


def _activity_from_api(
    raw_activity: dict[str, Any], data_dir: Path
) -> tuple[Activity, date]:
    try:
        activity_id = int(raw_activity["activityId"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("ID de actividad inválido") from error
    if activity_id < 1:
        raise ValueError("ID de actividad inválido")

    timestamp = raw_activity.get("startTimeLocal") or raw_activity.get("startTimeGMT")
    try:
        activity_date = date.fromisoformat(str(timestamp)[:10])
    except ValueError as error:
        raise ValueError("fecha de actividad inválida") from error

    activity_type = raw_activity.get("activityType") or {}
    sport = activity_type.get("typeKey") or "unknown"
    destination = fit_path(data_dir, activity_id, activity_date)
    return (
        Activity(
            garmin_id=activity_id,
            date=str(timestamp),
            sport=str(sport),
            name=str(raw_activity.get("activityName") or ""),
            fit_path=destination,
        ),
        activity_date,
    )
