from swimops.activities import format_activities, get_activities


def test_get_activities_requests_requested_page_size() -> None:
    class Client:
        def get_activities(self, start: int, limit: int) -> list[dict[str, object]]:
            assert (start, limit) == (0, 3)
            return []

    assert get_activities(Client(), 3) == []  # type: ignore[arg-type]


def test_format_activities_outputs_useful_fields() -> None:
    output = format_activities(
        [
            {
                "activityId": 123,
                "startTimeLocal": "2026-09-08 18:30:00",
                "activityType": {"typeKey": "lap_swimming"},
                "distance": 2000.4,
                "duration": 3600.2,
                "activityName": "Piscina\nseries",
            }
        ]
    )

    assert output.splitlines() == [
        "ID\tFECHA\tDEPORTE\tDISTANCIA_M\tDURACION_S\tNOMBRE",
        "123\t2026-09-08 18:30:00\tlap_swimming\t2000\t3600\tPiscina series",
    ]
