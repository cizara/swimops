import pytest
from pydantic import ValidationError

from swimops.workouts import (
    SwimWorkout,
    format_garmin_workouts,
    get_garmin_workout,
    list_garmin_workouts,
    workout_preview,
)


WORKOUT = {
    "name": "CSS intervals",
    "pool_length_m": 25,
    "steps": [
        {"type": "warmup", "distance_m": 400},
        {
            "type": "repeat",
            "repeat": 8,
            "steps": [
                {
                    "type": "swim",
                    "distance_m": 100,
                    "stroke": "freestyle",
                    "target": {"type": "pace", "min": "1:42", "max": "1:48"},
                },
                {"type": "rest", "duration_s": 20},
            ],
        },
        {"type": "cooldown", "distance_m": 300},
    ],
}


def test_validates_and_previews_workout() -> None:
    preview = workout_preview(SwimWorkout.model_validate(WORKOUT))

    assert preview["total_distance_m"] == 1500
    assert preview["total_rest_s"] == 160
    assert "2. Repetir 8 veces:" in preview["text"]
    assert "ritmo 1:42–1:48/100 m" in preview["text"]


def test_rejects_distance_that_does_not_match_pool() -> None:
    workout = {**WORKOUT, "steps": [{"type": "swim", "distance_m": 110}]}

    with pytest.raises(ValidationError, match="múltiplos de la longitud"):
        SwimWorkout.model_validate(workout)


def test_rejects_invalid_pace_range() -> None:
    workout = {
        **WORKOUT,
        "steps": [
            {
                "type": "swim",
                "distance_m": 100,
                "target": {"type": "pace", "min": "1:50", "max": "1:40"},
            }
        ],
    }

    with pytest.raises(ValidationError, match="ritmo mínimo"):
        SwimWorkout.model_validate(workout)


class GarminClient:
    def get_workouts(self, start: int, limit: int):
        assert (start, limit) == (0, 2)
        return [
            {
                "workoutId": 123,
                "workoutName": "Día A",
                "sportType": {"sportTypeKey": "swimming"},
                "estimatedDistanceInMeters": 1500.0,
                "estimatedDurationInSecs": 0,
                "poolLength": 25.0,
                "updateDate": "2026-09-09T10:00:00.0",
            }
        ]

    def get_workout_by_id(self, workout_id: int):
        assert workout_id == 123
        return {
            **self.get_workouts(0, 2)[0],
            "description": "Técnica",
            "createdDate": "2026-09-01T10:00:00.0",
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "workoutSteps": [
                        {
                            "type": "ExecutableStepDTO",
                            "stepOrder": 1,
                            "stepType": {"stepTypeKey": "warmup"},
                            "endCondition": {"conditionTypeKey": "distance"},
                            "endConditionValue": 300,
                            "strokeType": {"strokeTypeKey": "mixed"},
                        }
                    ],
                }
            ],
            "author": {"fullName": "Private"},
        }


def test_lists_compact_garmin_workouts() -> None:
    workouts = list_garmin_workouts(GarminClient(), 2)

    assert workouts == [
        {
            "workout_id": 123,
            "name": "Día A",
            "sport": "swimming",
            "distance_m": 1500.0,
            "duration_s": 0,
            "pool_length_m": 25.0,
            "updated_at": "2026-09-09T10:00:00.0",
        }
    ]
    assert format_garmin_workouts(workouts).splitlines()[1] == (
        "123\tswimming\t1500\t25\tDía A"
    )


def test_gets_workout_segments_without_personal_metadata() -> None:
    workout = get_garmin_workout(GarminClient(), 123)

    assert workout["description"] == "Técnica"
    assert workout["segments"] == [
        {
            "segment_order": 1,
            "steps": [
                {
                    "order": 1,
                    "type": "warmup",
                    "distance_m": 300,
                    "stroke": "mixed",
                }
            ],
        }
    ]
    assert "author" not in workout
