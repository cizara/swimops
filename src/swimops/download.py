from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Protocol

from garminconnect import Garmin


class GarminDownloadClient(Protocol):
    def download_activity(
        self, activity_id: str, dl_fmt: Garmin.ActivityDownloadFormat
    ) -> bytes: ...


class FitDownloadError(RuntimeError):
    pass


def fit_path(data_dir: Path, activity_id: int | str, activity_date: date) -> Path:
    identifier = _activity_id(activity_id)
    return Path(data_dir) / "fit" / f"{activity_date:%Y}" / f"{activity_date:%m}" / (
        f"{identifier}.fit"
    )


def download_fit(
    client: GarminDownloadClient,
    activity_id: int | str,
    activity_date: date,
    data_dir: Path,
) -> Path:
    """Download an activity's original FIT and return its local path.

    Existing files are returned unchanged.  New files become visible only after
    their complete contents have been written and synced to disk.
    """
    destination = fit_path(data_dir, activity_id, activity_date)
    if destination.is_file():
        return destination

    original = client.download_activity(
        str(_activity_id(activity_id)), Garmin.ActivityDownloadFormat.ORIGINAL
    )
    contents = _fit_from_original(original)
    _write_new_file(destination, contents)
    return destination


def _activity_id(activity_id: int | str) -> int:
    try:
        identifier = int(activity_id)
    except (TypeError, ValueError) as error:
        raise ValueError("activity_id debe ser un entero positivo") from error
    if identifier < 1:
        raise ValueError("activity_id debe ser un entero positivo")
    return identifier


def _fit_from_original(original: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            fit_files = [info for info in archive.infolist() if info.filename.lower().endswith(".fit")]
            if len(fit_files) != 1:
                raise FitDownloadError("El original de Garmin no contiene un único archivo FIT.")
            return archive.read(fit_files[0])
    except zipfile.BadZipFile as error:
        raise FitDownloadError("El original descargado de Garmin no es un archivo ZIP válido.") from error


def _write_new_file(destination: Path, contents: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(contents)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            return
        _sync_directory(destination.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
