from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from garmin_fit_sdk import Decoder, Stream


class SwimParseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SwimSession:
    activity_id: int
    pool_length_m: float
    total_lengths: int
    active_lengths: int
    distance_m: float
    elapsed_time_s: float
    timer_time_s: float
    swim_time_s: float
    avg_pace_100m: float | None
    avg_hr: int | None
    max_hr: int | None
    total_strokes: int
    avg_strokes_per_length: float | None
    avg_swolf: float | None


@dataclass(frozen=True, slots=True)
class SwimLap:
    activity_id: int
    lap_index: int
    workout_step_index: int | None
    distance_m: float
    elapsed_time_s: float
    timer_time_s: float
    swim_time_s: float
    pace_100m: float | None
    stroke_type: str | None
    stroke_count: int
    active_lengths: int
    avg_hr: int | None
    max_hr: int | None
    avg_swolf: float | None


@dataclass(frozen=True, slots=True)
class SwimLength:
    activity_id: int
    length_index: int
    length_type: str
    distance_m: float
    duration_s: float
    stroke_type: str | None
    stroke_count: int | None
    swolf: float | None


@dataclass(frozen=True, slots=True)
class HrZone:
    activity_id: int
    zone: int
    seconds: float
    high_boundary_bpm: int | None


@dataclass(frozen=True, slots=True)
class ParsedSwim:
    session: SwimSession
    laps: tuple[SwimLap, ...]
    lengths: tuple[SwimLength, ...]
    hr_zones: tuple[HrZone, ...]


def parse_swim_fit(path: Path, activity_id: int) -> ParsedSwim:
    messages, errors = Decoder(Stream.from_file(str(path))).read()
    if errors:
        raise SwimParseError(f"Invalid FIT: {errors[0]}")
    return parse_swim_messages(messages, activity_id)


def parse_swim_messages(messages: dict[str, list[dict[str, Any]]], activity_id: int) -> ParsedSwim:
    sessions = messages.get("session_mesgs", [])
    if len(sessions) != 1:
        raise SwimParseError("The FIT file must contain exactly one session.")
    raw_session = sessions[0]
    if raw_session.get("sub_sport") != "lap_swimming":
        raise SwimParseError("The activity is not pool swimming.")

    pool_length = _float(raw_session, "pool_length")
    if pool_length <= 0:
        raise SwimParseError("The pool length is invalid.")

    lengths = tuple(
        _parse_length(raw, activity_id, pool_length, index)
        for index, raw in enumerate(messages.get("length_mesgs", []))
    )
    active_lengths = tuple(length for length in lengths if length.length_type == "active")
    distance = _float(raw_session, "total_distance")
    swim_time = _float(raw_session, "active_time")
    total_strokes = _int(raw_session, "total_strokes")

    session = SwimSession(
        activity_id=activity_id,
        pool_length_m=pool_length,
        total_lengths=_int(raw_session, "num_lengths"),
        active_lengths=_int(raw_session, "num_active_lengths"),
        distance_m=distance,
        elapsed_time_s=_float(raw_session, "total_elapsed_time"),
        timer_time_s=_float(raw_session, "total_timer_time"),
        swim_time_s=swim_time,
        avg_pace_100m=_pace(swim_time, distance),
        avg_hr=_optional_int(raw_session.get("avg_heart_rate")),
        max_hr=_optional_int(raw_session.get("max_heart_rate")),
        total_strokes=total_strokes,
        avg_strokes_per_length=(
            total_strokes / len(active_lengths) if active_lengths else None
        ),
        avg_swolf=_average(
            length.swolf for length in active_lengths if length.swolf is not None
        ),
    )
    laps = tuple(
        _parse_lap(raw, activity_id, lengths, index)
        for index, raw in enumerate(messages.get("lap_mesgs", []))
    )
    return ParsedSwim(
        session=session,
        laps=laps,
        lengths=lengths,
        hr_zones=_parse_hr_zones(messages, activity_id),
    )


def _parse_length(
    raw: dict[str, Any], activity_id: int, pool_length: float, fallback_index: int
) -> SwimLength:
    length_type = str(raw.get("length_type") or "unknown")
    duration = _float(raw, "total_timer_time")
    strokes = _optional_int(raw.get("total_strokes"))
    return SwimLength(
        activity_id=activity_id,
        length_index=_optional_int(raw.get("message_index")) or fallback_index,
        length_type=length_type,
        distance_m=pool_length if length_type == "active" else 0.0,
        duration_s=duration,
        stroke_type=_optional_string(raw.get("swim_stroke")),
        stroke_count=strokes,
        swolf=duration + strokes if length_type == "active" and strokes is not None else None,
    )


def _parse_lap(
    raw: dict[str, Any], activity_id: int, lengths: tuple[SwimLength, ...], fallback_index: int
) -> SwimLap:
    first = _optional_int(raw.get("first_length_index")) or 0
    count = _optional_int(raw.get("num_lengths")) or 0
    lap_lengths = lengths[first : first + count]
    swolf_values = [
        length.swolf
        for length in lap_lengths
        if length.length_type == "active" and length.swolf is not None
    ]
    distance = _float(raw, "total_distance")
    swim_time = _float(raw, "active_time")
    return SwimLap(
        activity_id=activity_id,
        lap_index=_optional_int(raw.get("message_index")) or fallback_index,
        workout_step_index=_optional_int(raw.get("wkt_step_index")),
        distance_m=distance,
        elapsed_time_s=_float(raw, "total_elapsed_time"),
        timer_time_s=_float(raw, "total_timer_time"),
        swim_time_s=swim_time,
        pace_100m=_pace(swim_time, distance),
        stroke_type=_optional_string(raw.get("swim_stroke")),
        stroke_count=_int(raw, "total_strokes"),
        active_lengths=_int(raw, "num_active_lengths"),
        avg_hr=_optional_int(raw.get("avg_heart_rate")),
        max_hr=_optional_int(raw.get("max_heart_rate")),
        avg_swolf=_average(swolf_values),
    )


def _parse_hr_zones(
    messages: dict[str, list[dict[str, Any]]], activity_id: int
) -> tuple[HrZone, ...]:
    session_zone = next(
        (
            zone
            for zone in messages.get("time_in_zone_mesgs", [])
            if zone.get("reference_mesg") == "session"
        ),
        None,
    )
    if session_zone is None:
        return ()
    seconds = session_zone.get("time_in_hr_zone") or []
    boundaries = session_zone.get("hr_zone_high_boundary") or []
    return tuple(
        HrZone(
            activity_id=activity_id,
            zone=index,
            seconds=float(value),
            high_boundary_bpm=_optional_int(
                boundaries[index] if index < len(boundaries) else None
            ),
        )
        for index, value in enumerate(seconds)
    )


def _float(message: dict[str, Any], field: str) -> float:
    value = message.get(field, 0)
    return float(value) if value is not None else 0.0


def _int(message: dict[str, Any], field: str) -> int:
    value = message.get(field, 0)
    return int(value) if value is not None else 0


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _pace(seconds: float, distance_m: float) -> float | None:
    return seconds * 100 / distance_m if distance_m > 0 else None


def _average(values: Any) -> float | None:
    collected = list(values)
    return fmean(collected) if collected else None
