from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest
from garminconnect import Garmin

from swimops.download import FitDownloadError, download_fit, fit_path


def original_with_fit(contents: bytes = b"FIT bytes") -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("activity.fit", contents)
    return result.getvalue()


def test_fit_path_uses_year_month_and_activity_id(tmp_path: Path) -> None:
    assert fit_path(tmp_path, 123, date(2026, 4, 15)) == tmp_path / "fit/2026/04/123.fit"


def test_download_fit_extracts_original_to_expected_path(tmp_path: Path) -> None:
    calls: list[tuple[str, Garmin.ActivityDownloadFormat]] = []

    class Client:
        def download_activity(self, activity_id: str, dl_fmt: Garmin.ActivityDownloadFormat) -> bytes:
            calls.append((activity_id, dl_fmt))
            return original_with_fit(b"original FIT")

    result = download_fit(Client(), 123, date(2026, 4, 15), tmp_path)

    assert result == tmp_path / "fit/2026/04/123.fit"
    assert result.read_bytes() == b"original FIT"
    assert calls == [("123", Garmin.ActivityDownloadFormat.ORIGINAL)]


def test_download_fit_keeps_existing_file_without_requesting_garmin(tmp_path: Path) -> None:
    existing = fit_path(tmp_path, 123, date(2026, 4, 15))
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already downloaded")

    class Client:
        def download_activity(self, activity_id: str, dl_fmt: Garmin.ActivityDownloadFormat) -> bytes:
            raise AssertionError("must not download an existing file")

    assert download_fit(Client(), 123, date(2026, 4, 15), tmp_path) == existing
    assert existing.read_bytes() == b"already downloaded"


def test_download_fit_leaves_no_final_file_when_original_is_invalid(tmp_path: Path) -> None:
    class Client:
        def download_activity(self, activity_id: str, dl_fmt: Garmin.ActivityDownloadFormat) -> bytes:
            return b"not a zip"

    with pytest.raises(FitDownloadError, match="valid ZIP"):
        download_fit(Client(), 123, date(2026, 4, 15), tmp_path)

    assert not fit_path(tmp_path, 123, date(2026, 4, 15)).exists()


def test_download_fit_does_not_overwrite_file_created_during_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = fit_path(tmp_path, 123, date(2026, 4, 15))

    class Client:
        def download_activity(self, activity_id: str, dl_fmt: Garmin.ActivityDownloadFormat) -> bytes:
            return original_with_fit(b"new download")

    def link_after_competing_download(source: Path, target: Path) -> None:
        Path(target).write_bytes(b"other download")
        raise FileExistsError

    monkeypatch.setattr("swimops.download.os.link", link_after_competing_download)

    result = download_fit(Client(), 123, date(2026, 4, 15), tmp_path)

    assert result == destination
    assert destination.read_bytes() == b"other download"
