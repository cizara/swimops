from __future__ import annotations

import pytest

from swimops.swimming import SwimParseError, parse_swim_messages


def swim_messages() -> dict:
    return {
        "session_mesgs": [
            {
                "sub_sport": "lap_swimming",
                "pool_length": 25.0,
                "num_lengths": 3,
                "num_active_lengths": 2,
                "total_distance": 50.0,
                "total_elapsed_time": 65.0,
                "total_timer_time": 65.0,
                "active_time": 50.0,
                "avg_heart_rate": 130,
                "max_heart_rate": 155,
                "total_strokes": 22,
            }
        ],
        "length_mesgs": [
            {
                "message_index": 0,
                "length_type": "active",
                "total_timer_time": 25.0,
                "total_strokes": 10,
                "swim_stroke": "freestyle",
            },
            {
                "message_index": 1,
                "length_type": "idle",
                "total_timer_time": 15.0,
            },
            {
                "message_index": 2,
                "length_type": "active",
                "total_timer_time": 30.0,
                "total_strokes": 12,
                "swim_stroke": "backstroke",
            },
        ],
        "lap_mesgs": [
            {
                "message_index": 0,
                "first_length_index": 0,
                "num_lengths": 2,
                "num_active_lengths": 1,
                "total_distance": 25.0,
                "total_elapsed_time": 40.0,
                "total_timer_time": 40.0,
                "active_time": 25.0,
                "total_strokes": 10,
                "avg_heart_rate": 125,
                "max_heart_rate": 145,
                "wkt_step_index": 3,
                "swim_stroke": "freestyle",
            },
            {
                "message_index": 1,
                "first_length_index": 2,
                "num_lengths": 1,
                "num_active_lengths": 1,
                "total_distance": 25.0,
                "total_elapsed_time": 30.0,
                "total_timer_time": 30.0,
                "active_time": 30.0,
                "total_strokes": 12,
            },
        ],
        "time_in_zone_mesgs": [
            {
                "reference_mesg": "session",
                "time_in_hr_zone": [5.0, 20.0, 25.0],
                "hr_zone_high_boundary": [100, 120, 140],
            }
        ],
    }


def test_parses_session_laps_lengths_and_hr_zones() -> None:
    swim = parse_swim_messages(swim_messages(), 123)

    assert swim.session.avg_pace_100m == 100.0
    assert swim.session.avg_strokes_per_length == 11.0
    assert swim.session.avg_swolf == 38.5
    assert len(swim.laps) == 2
    assert swim.laps[0].avg_swolf == 35.0
    assert swim.laps[0].workout_step_index == 3
    assert [length.swolf for length in swim.lengths] == [35.0, None, 42.0]
    assert [(zone.zone, zone.seconds) for zone in swim.hr_zones] == [
        (0, 5.0),
        (1, 20.0),
        (2, 25.0),
    ]


def test_rejects_non_pool_swim() -> None:
    messages = swim_messages()
    messages["session_mesgs"][0]["sub_sport"] = "open_water"

    with pytest.raises(SwimParseError, match="pool swimming"):
        parse_swim_messages(messages, 123)
