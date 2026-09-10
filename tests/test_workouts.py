import pytest
from pydantic import ValidationError

from swimops.workouts import (
    SwimWorkout,
    create_garmin_swim_workout,
    format_garmin_workouts,
    get_garmin_workout,
    list_garmin_workouts,
    to_garmin_workout,
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
                    "equipment": "paddles",
                    "target": {"type": "pace", "pace": "1:45"},
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
    assert preview["total_rest_s"] == 140
    assert preview["manual_rests"] == 2
    assert preview["text"].count("Descanso — hasta botón Lap") == 2
    assert "3. Repetir 8 veces:" in preview["text"]
    assert "ritmo 1:45/100 m" in preview["text"]
    assert "equipo: paddles" in preview["text"]


def test_rejects_distance_that_does_not_match_pool() -> None:
    workout = {**WORKOUT, "steps": [{"type": "swim", "distance_m": 110}]}

    with pytest.raises(ValidationError, match="múltiplos de la longitud"):
        SwimWorkout.model_validate(workout)


def test_rejects_invalid_pace() -> None:
    workout = {
        **WORKOUT,
        "steps": [
            {
                "type": "swim",
                "distance_m": 100,
                "target": {"type": "pace", "pace": "1:75"},
            }
        ],
    }

    with pytest.raises(ValidationError, match="formato M:SS"):
        SwimWorkout.model_validate(workout)


def test_converts_workout_to_garmin_payload() -> None:
    payload = to_garmin_workout(SwimWorkout.model_validate(WORKOUT))
    steps = payload["workoutSegments"][0]["workoutSteps"]
    repeated = steps[2]
    swim, rest = repeated["workoutSteps"]

    assert payload["estimatedDistanceInMeters"] == 1500
    assert payload["poolLength"] == 25
    assert [step["stepOrder"] for step in steps] == [1, 2, 3, 6, 7]
    assert steps[1]["endCondition"]["conditionTypeKey"] == "lap.button"
    assert steps[3]["endCondition"]["conditionTypeKey"] == "lap.button"
    assert repeated["numberOfIterations"] == 8
    assert repeated["skipLastRestStep"] is True
    assert swim["stepOrder"] == 4
    assert swim["strokeType"]["strokeTypeKey"] == "free"
    assert swim["equipmentType"]["equipmentTypeKey"] == "paddles"
    assert swim["secondaryTargetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert swim["secondaryTargetValueOne"] == pytest.approx(100 / 105)
    assert rest["stepOrder"] == 5
    assert rest["endCondition"]["conditionTypeKey"] == "fixed.rest"
    assert rest["endConditionValue"] == 20


def test_can_disable_default_rests() -> None:
    workout = SwimWorkout.model_validate(
        {**WORKOUT, "auto_rest_between_steps": False}
    )

    preview = workout_preview(workout)
    payload = to_garmin_workout(workout)

    assert preview["manual_rests"] == 0
    assert [
        step["stepType"]["stepTypeKey"]
        for step in payload["workoutSegments"][0]["workoutSteps"]
    ] == ["warmup", "repeat", "cooldown"]


@pytest.mark.parametrize(
    ("equipment", "garmin_key"),
    [
        ("paddles", "paddles"),
        ("fins", "fins"),
        ("pull_buoy", "pull_buoy"),
        ("kickboard", "kickboard"),
        ("snorkel", "snorkel"),
    ],
)
def test_maps_available_equipment(equipment: str, garmin_key: str) -> None:
    workout = SwimWorkout.model_validate(
        {
            "name": "Material",
            "pool_length_m": 25,
            "steps": [
                {"type": "swim", "distance_m": 100, "equipment": equipment}
            ],
        }
    )

    step = to_garmin_workout(workout)["workoutSegments"][0]["workoutSteps"][0]

    assert step["equipmentType"]["equipmentTypeKey"] == garmin_key


def test_creates_workout_and_returns_compact_result() -> None:
    class UploadClient:
        payload = None

        def upload_workout(self, payload):
            self.payload = payload
            return {"workoutId": 456, "workoutName": "CSS intervals"}

    client = UploadClient()
    result = create_garmin_swim_workout(
        client, SwimWorkout.model_validate(WORKOUT)
    )

    assert client.payload["workoutName"] == "CSS intervals"
    assert result == {
        "workout_id": 456,
        "name": "CSS intervals",
        "sport": "swimming",
        "distance_m": 1500,
        "pool_length_m": 25,
    }


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
