import pytest
from pydantic import ValidationError

from swimops.workouts import SwimWorkout, workout_preview


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
