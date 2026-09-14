from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

from garminconnect import Garmin
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


PACE_PATTERN = re.compile(r"^(\d+):(\d{2})$")
Stroke = Literal[
    "any",
    "freestyle",
    "backstroke",
    "breaststroke",
    "butterfly",
    "individual_medley",
    "mixed",
]
Equipment = Literal["fins", "kickboard", "paddles", "pull_buoy", "snorkel"]
Drill = Literal["kick", "pull", "drill"]


def pace_seconds(value: str) -> int:
    match = PACE_PATTERN.fullmatch(value)
    if not match or int(match.group(2)) > 59:
        raise ValueError("pace must use M:SS format")
    seconds = int(match.group(1)) * 60 + int(match.group(2))
    if seconds == 0:
        raise ValueError("pace must be greater than zero")
    return seconds


class PaceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["pace"] = "pace"
    pace: str

    @model_validator(mode="after")
    def valid_pace(self) -> PaceTarget:
        pace_seconds(self.pace)
        return self


class SwimStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["warmup", "swim", "cooldown"]
    distance_m: PositiveInt
    stroke: Stroke | None = None
    equipment: Equipment | None = None
    drill: Drill | None = None
    notes: str | None = Field(default=None, max_length=200)
    target: PaceTarget | None = None


class RestStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["rest"]
    duration_s: PositiveInt | None = None


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
    auto_rest_between_steps: bool = True
    steps: list[WorkoutStep] = Field(min_length=1)

    @model_validator(mode="after")
    def distances_match_pool(self) -> SwimWorkout:
        swim_steps = list(_swim_steps(self.steps))
        if not swim_steps:
            raise ValueError("the workout must include at least one swim step")
        invalid = [
            step.distance_m
            for step in swim_steps
            if step.distance_m % self.pool_length_m
        ]
        if invalid:
            raise ValueError(
                "distances must be multiples of the pool length: "
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
        raise ValueError("limit must be greater than zero")
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


def to_garmin_workout(workout: SwimWorkout) -> dict[str, Any]:
    sport = {"sportTypeId": 4, "sportTypeKey": "swimming", "displayOrder": 3}
    order = 1
    steps = _with_default_rests(
        workout.steps, enabled=workout.auto_rest_between_steps
    )

    def convert(step: WorkoutStep | BasicStep) -> dict[str, Any]:
        nonlocal order
        step_order = order
        order += 1
        if isinstance(step, RepeatStep):
            children = [convert(child) for child in step.steps]
            return {
                "type": "RepeatGroupDTO",
                "stepOrder": step_order,
                "stepType": {
                    "stepTypeId": 6,
                    "stepTypeKey": "repeat",
                    "displayOrder": 6,
                },
                "numberOfIterations": step.repeat,
                "workoutSteps": children,
                "endCondition": {
                    "conditionTypeId": 7,
                    "conditionTypeKey": "iterations",
                    "displayOrder": 7,
                    "displayable": False,
                },
                "endConditionValue": float(step.repeat),
                "skipLastRestStep": isinstance(step.steps[-1], RestStep),
                "smartRepeat": False,
            }
        if isinstance(step, RestStep):
            return _garmin_rest(step, step_order)
        return _garmin_swim_step(step, step_order)

    return {
        "workoutName": workout.name,
        "sportType": sport,
        "estimatedDurationInSecs": 0,
        "estimatedDistanceInMeters": float(_distance(workout.steps)),
        "poolLength": float(workout.pool_length_m),
        "poolLengthUnit": {"unitId": 1, "unitKey": "meter", "factor": 100.0},
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": sport,
                "workoutSteps": [convert(step) for step in steps],
            }
        ],
    }


def create_garmin_swim_workout(
    client: Garmin, workout: SwimWorkout
) -> dict[str, Any]:
    created = client.upload_workout(to_garmin_workout(workout))
    workout_id = created.get("workoutId")
    if not workout_id:
        raise ValueError("Garmin did not return the created workout ID")
    return {
        "workout_id": workout_id,
        "name": created.get("workoutName", workout.name),
        "sport": (created.get("sportType") or {}).get("sportTypeKey", "swimming"),
        "distance_m": created.get(
            "estimatedDistanceInMeters", _distance(workout.steps)
        ),
        "pool_length_m": created.get("poolLength", workout.pool_length_m),
    }


def _garmin_swim_step(step: SwimStep, order: int) -> dict[str, Any]:
    step_types = {
        "warmup": (1, "warmup", 1),
        "swim": (8, "main", 8),
        "cooldown": (2, "cooldown", 2),
    }
    step_type = (3, "interval", 3) if step.drill else step_types[step.type]
    result: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {
            "stepTypeId": step_type[0],
            "stepTypeKey": step_type[1],
            "displayOrder": step_type[2],
        },
        "endCondition": {
            "conditionTypeId": 3,
            "conditionTypeKey": "distance",
            "displayOrder": 3,
            "displayable": True,
        },
        "endConditionValue": float(step.distance_m),
        "preferredEndConditionUnit": {
            "unitId": 1,
            "unitKey": "meter",
            "factor": 100.0,
        },
        "targetType": {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        },
        "equipmentType": _named_type(step.equipment, EQUIPMENT_TYPES),
    }
    if step.stroke:
        result["strokeType"] = _named_type(step.stroke, STROKE_TYPES)
    if step.drill:
        result["drillType"] = _named_type(step.drill, DRILL_TYPES)
    if step.notes:
        result["description"] = step.notes
    if step.target:
        result["secondaryTargetType"] = {
            "workoutTargetTypeId": 6,
            "workoutTargetTypeKey": "pace.zone",
            "displayOrder": 6,
        }
        result["secondaryTargetValueOne"] = 100 / pace_seconds(step.target.pace)
    return result


def _garmin_rest(step: RestStep, order: int) -> dict[str, Any]:
    timed = step.duration_s is not None
    result: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
        "endCondition": {
            "conditionTypeId": 8 if timed else 1,
            "conditionTypeKey": "fixed.rest" if timed else "lap.button",
            "displayOrder": 8 if timed else 1,
            "displayable": True,
        },
        "targetType": {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        },
        "equipmentType": {"equipmentTypeId": 0, "displayOrder": 0},
    }
    if step.duration_s is not None:
        result["endConditionValue"] = float(step.duration_s)
    return result


STROKE_TYPES = {
    "any": (1, "any_stroke", 1),
    "backstroke": (2, "backstroke", 2),
    "breaststroke": (3, "breaststroke", 3),
    "butterfly": (5, "fly", 5),
    "freestyle": (6, "free", 6),
    "individual_medley": (7, "individual_medley", 7),
    "mixed": (8, "mixed", 8),
}
EQUIPMENT_TYPES = {
    "fins": (1, "fins", 1),
    "kickboard": (2, "kickboard", 2),
    "paddles": (3, "paddles", 3),
    "pull_buoy": (4, "pull_buoy", 4),
    "snorkel": (5, "snorkel", 5),
}
DRILL_TYPES = {
    "kick": (1, "kick", 1),
    "pull": (2, "pull", 2),
    "drill": (3, "drill", 3),
}


def _named_type(
    name: str | None, choices: dict[str, tuple[int, str, int]]
) -> dict[str, Any]:
    if name is None:
        return {"equipmentTypeId": 0, "displayOrder": 0}
    value = choices[name]
    if choices is STROKE_TYPES:
        prefix = "stroke"
    elif choices is DRILL_TYPES:
        prefix = "drill"
    else:
        prefix = "equipment"
    return {
        f"{prefix}TypeId": value[0],
        f"{prefix}TypeKey": value[1],
        "displayOrder": value[2],
    }


def format_garmin_workouts(workouts: list[dict[str, Any]]) -> str:
    lines = ["ID\tSPORT\tDISTANCE_M\tPOOL_M\tNAME"]
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
    elif condition in ("time", "fixed.rest"):
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
    secondary = (step.get("secondaryTargetType") or {}).get("workoutTargetTypeKey")
    if secondary:
        result["target"] = {
            "type": secondary,
            "value_one": step.get("secondaryTargetValueOne"),
            "value_two": step.get("secondaryTargetValueTwo"),
            "unit": (step.get("secondaryTargetValueUnit") or {}).get("unitKey"),
        }
    return result


def _display_number(value: Any) -> str:
    if not isinstance(value, int | float):
        return ""
    return f"{value:g}"


def workout_preview(workout: SwimWorkout) -> dict[str, Any]:
    steps = _with_default_rests(
        workout.steps, enabled=workout.auto_rest_between_steps
    )
    lines = [
        workout.name,
        f"Pool: {workout.pool_length_m} m",
        f"Total distance: {_distance(workout.steps)} m",
    ]
    rest = _rest_seconds(steps)
    if rest:
        lines.append(f"Timed rest: {_duration(rest)}")
    lines.append("")
    for index, step in enumerate(steps, 1):
        lines.extend(_render_step(step, f"{index}. "))
    return {
        "name": workout.name,
        "pool_length_m": workout.pool_length_m,
        "total_distance_m": _distance(workout.steps),
        "total_rest_s": rest,
        "manual_rests": sum(
            isinstance(step, RestStep) and step.duration_s is None for step in steps
        ),
        "text": "\n".join(lines),
    }


def _with_default_rests(
    steps: list[WorkoutStep], enabled: bool
) -> list[WorkoutStep]:
    if not enabled:
        return list(steps)
    result: list[WorkoutStep] = []
    for step in steps:
        if (
            result
            and not isinstance(result[-1], RestStep)
            and not isinstance(step, RestStep)
        ):
            result.append(RestStep(type="rest"))
        result.append(step)
    return result


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
            total += step.duration_s or 0
        elif isinstance(step, RepeatStep):
            repeated = step.repeat * _rest_seconds(step.steps)
            if isinstance(step.steps[-1], RestStep):
                repeated -= step.steps[-1].duration_s or 0
            total += repeated
    return total


def _render_step(step: WorkoutStep | BasicStep, prefix: str) -> list[str]:
    if isinstance(step, RepeatStep):
        lines = [f"{prefix}Repeat {step.repeat} times:"]
        for child in step.steps:
            lines.extend(_render_step(child, "   - "))
        return lines
    if isinstance(step, RestStep):
        duration = _duration(step.duration_s) if step.duration_s else "until Lap button"
        return [f"{prefix}Rest — {duration}"]

    labels = {
        "warmup": "Warm-up",
        "swim": "Swim",
        "cooldown": "Cool-down",
    }
    strokes = {
        "any": "any stroke",
        "freestyle": "freestyle",
        "backstroke": "backstroke",
        "breaststroke": "breaststroke",
        "butterfly": "butterfly",
        "individual_medley": "individual medley",
        "mixed": "mixed",
    }
    parts = [labels[step.type], f"{step.distance_m} m"]
    if step.stroke:
        parts.append(strokes[step.stroke])
    if step.drill:
        parts.append(f"drill: {step.drill}")
    if step.equipment:
        parts.append(f"equipment: {step.equipment}")
    if step.target:
        parts.append(f"pace {step.target.pace}/100 m")
    if step.notes:
        parts.append(step.notes)
    return [prefix + " — ".join(parts)]


def _duration(seconds: int) -> str:
    minutes, remaining = divmod(seconds, 60)
    if minutes and remaining:
        return f"{minutes} min {remaining} s"
    if minutes:
        return f"{minutes} min"
    return f"{remaining} s"
