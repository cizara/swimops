import pytest

from swimops.cli import build_parser, positive_int


def test_activities_defaults_to_ten() -> None:
    args = build_parser().parse_args(["activities"])
    assert args.limit == 10


def test_limit_must_be_positive() -> None:
    with pytest.raises(Exception):
        positive_int("0")
