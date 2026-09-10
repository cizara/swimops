from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

from garminconnect import Garmin
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


PACE_PATTERN = re.compile(r"^(\d+):(\d{2})$")
Stroke = Literal[
    "freestyle", "backstroke", "breaststroke", "butterfly", "mixed", "drill"
]


def pace_seconds(value: str) -> int:
    match = PACE_PATTERN.fullmatch(value)
    if not match or int(match.group(2)) > 59:
        raise ValueError("el ritmo debe tener formato M:SS")
    seconds = int(match.group(1)) * 60 + int(match.group(2))
    if seconds == 0:
        raise ValueError("el ritmo debe ser mayor que cero")
    return seconds


class PaceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["pace"] = "pace"
    min: str
    max: str

    @model_validator(mode="after")
    def valid_range(self) -> PaceTarget:
        minimum = pace_seconds(self.min)
        maximum = pace_seconds(self.max)
        if minimum > maximum:
            raise ValueError("el ritmo mínimo no puede ser más lento que el máximo")
        return self


class SwimStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["warmup", "swim", "cooldown"]
    distance_m: PositiveInt
    stroke: Stroke | None = None
    target: PaceTarget | None = None


class RestStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["rest"]
    duration_s: PositiveInt


BasicStep = Annotated[SwimStep | RestStep, Field(discriminator="type")]


class RepeatStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["repeat"] = "repeat"
    repeat: PositiveInt
    steps: list[BasicStep] = Field(min_length=1)


WorkoutStep = Annotated[SwimStep | RestStep | RepeatStep, Field(discriminator="type")]


class SwimWorkout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    sport: Literal["swimming"] = "swimming"
    pool_length_m: PositiveInt
    steps: list[WorkoutStep] = Field(min_length=1)

    @model_validator(mode="after")
    def distances_match_pool(self) -> SwimWorkout:
        swim_steps = list(_swim_steps(self.steps))
        if not swim_steps:
            raise ValueError("la rutina debe incluir al menos un bloque de nado")
        invalid = [
            step.distance_m
            for step in swim_steps
            if step.distance_m % self.pool_length_m
        ]
        if invalid:
            raise ValueError(
                "las distancias deben ser múltiplos de la longitud de piscina: "
                + ", ".join(f"{distance} m" for distance in invalid)
            )
        return self


def _swim_steps(steps: list[WorkoutStep] | list[BasicStep]):
    for step in steps:
        if isinstance(step, SwimStep):
            yield step
        elif isinstance(step, RepeatStep):
            yield from _swim_steps(step.steps)


def load_workout(path: Path) -> SwimWorkout:
    return SwimWorkout.model_validate_json(path.read_text(encoding="utf-8"))


def list_garmin_workouts(client: Garmin, limit: int) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("el límite debe ser mayor que cero")
    return [_workout_summary(workout) for workout in client.get_workouts(0, limit)]


def get_garmin_workout(client: Garmin, workout_id: int) -> dict[str, Any]:
    workout = client.get_workout_by_id(workout_id)
    return {
        **_workout_summary(workout),
        "description": workout.get("description"),
        "created_at": workout.get("createdDate"),
        "segments": [
            {
                "segment_order": segment.get("segmentOrder"),
                "steps": [
                    _garmin_step(step) for step in segment.get("workoutSteps") or []
                ],
            }
            for segment in workout.get("workoutSegments") or []
        ],
    }


def format_garmin_workouts(workouts: list[dict[str, Any]]) -> str:
    lines = ["ID\tDEPORTE\tDISTANCIA_M\tPISCINA_M\tNOMBRE"]
    for workout in workouts:
        values = (
            workout["workout_id"],
            workout["sport"],
            _display_number(workout["distance_m"]),
            _display_number(workout["pool_length_m"]),
            str(workout["name"]).replace("\t", " ").replace("\n", " "),
        )
        lines.append("\t".join(map(str, values)))
    return "\n".join(lines)


def _workout_summary(workout: dict[str, Any]) -> dict[str, Any]:
    sport = workout.get("sportType") or {}
    return {
        "workout_id": workout.get("workoutId"),
        "name": workout.get("workoutName"),
        "sport": sport.get("sportTypeKey"),
        "distance_m": workout.get("estimatedDistanceInMeters"),
        "duration_s": workout.get("estimatedDurationInSecs"),
        "pool_length_m": workout.get("poolLength"),
        "updated_at": workout.get("updateDate"),
    }


def _garmin_step(step: dict[str, Any]) -> dict[str, Any]:
    if step.get("type") == "RepeatGroupDTO" or "numberOfIterations" in step:
        return {
            "order": step.get("stepOrder"),
            "type": "repeat",
            "repeat": step.get("numberOfIterations"),
            "steps": [_garmin_step(child) for child in step.get("workoutSteps") or []],
        }

    result = {
        "order": step.get("stepOrder"),
        "type": (step.get("stepType") or {}).get("stepTypeKey"),
    }
    condition = (step.get("endCondition") or {}).get("conditionTypeKey")
    value = step.get("endConditionValue")
    if condition == "distance":
        result["distance_m"] = value
    elif condition == "time":
        result["duration_s"] = value
    elif condition:
        result["end_condition"] = condition

    optional = {
        "description": step.get("description"),
        "stroke": (step.get("strokeType") or {}).get("strokeTypeKey"),
        "equipment": (step.get("equipmentType") or {}).get("equipmentTypeKey"),
        "drill": (step.get("drillType") or {}).get("drillTypeKey"),
    }
    result.update({key: item for key, item in optional.items() if item})

    target = (step.get("targetType") or {}).get("workoutTargetTypeKey")
    if target and target != "no.target":
        result["target"] = {
            "type": target,
            "value_one": step.get("targetValueOne"),
            "value_two": step.get("targetValueTwo"),
            "unit": (step.get("targetValueUnit") or {}).get("unitKey"),
        }
    return result


def _display_number(value: Any) -> str:
    if not isinstance(value, int | float):
        return ""
    return f"{value:g}"


def workout_preview(workout: SwimWorkout) -> dict[str, Any]:
    lines = [
        workout.name,
        f"Piscina: {workout.pool_length_m} m",
        f"Distancia total: {_distance(workout.steps)} m",
    ]
    rest = _rest_seconds(workout.steps)
    if rest:
        lines.append(f"Descanso programado: {_duration(rest)}")
    lines.append("")
    for index, step in enumerate(workout.steps, 1):
        lines.extend(_render_step(step, f"{index}. "))
    return {
        "name": workout.name,
        "pool_length_m": workout.pool_length_m,
        "total_distance_m": _distance(workout.steps),
        "total_rest_s": rest,
        "text": "\n".join(lines),
    }


def _distance(steps: list[WorkoutStep] | list[BasicStep]) -> int:
    total = 0
    for step in steps:
        if isinstance(step, SwimStep):
            total += step.distance_m
        elif isinstance(step, RepeatStep):
            total += step.repeat * _distance(step.steps)
    return total


def _rest_seconds(steps: list[WorkoutStep] | list[BasicStep]) -> int:
    total = 0
    for step in steps:
        if isinstance(step, RestStep):
            total += step.duration_s
        elif isinstance(step, RepeatStep):
            total += step.repeat * _rest_seconds(step.steps)
    return total


def _render_step(step: WorkoutStep | BasicStep, prefix: str) -> list[str]:
    if isinstance(step, RepeatStep):
        lines = [f"{prefix}Repetir {step.repeat} veces:"]
        for child in step.steps:
            lines.extend(_render_step(child, "   - "))
        return lines
    if isinstance(step, RestStep):
        return [f"{prefix}Descanso — {_duration(step.duration_s)}"]

    labels = {
        "warmup": "Calentamiento",
        "swim": "Nado",
        "cooldown": "Vuelta a la calma",
    }
    strokes = {
        "freestyle": "libre",
        "backstroke": "espalda",
        "breaststroke": "braza",
        "butterfly": "mariposa",
        "mixed": "mixto",
        "drill": "técnica",
    }
    parts = [labels[step.type], f"{step.distance_m} m"]
    if step.stroke:
        parts.append(strokes[step.stroke])
    if step.target:
        parts.append(f"ritmo {step.target.min}–{step.target.max}/100 m")
    return [prefix + " — ".join(parts)]


def _duration(seconds: int) -> str:
    minutes, remaining = divmod(seconds, 60)
    if minutes and remaining:
        return f"{minutes} min {remaining} s"
    if minutes:
        return f"{minutes} min"
    return f"{remaining} s"
