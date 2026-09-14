from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from swimops.activities import format_activities, get_activities
from swimops.auth import SessionNotFoundError, load_session, login, token_store_path
from swimops.processing import parse_swims
from swimops.sync import sync_activities
from swimops.workouts import (
    create_garmin_swim_workout,
    format_garmin_workouts,
    get_garmin_workout,
    list_garmin_workouts,
    load_workout,
    workout_preview,
)


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must use YYYY-MM-DD format") from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("must use YYYY-MM-DD format")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="garmin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="sign in and save tokens locally")
    activities = commands.add_parser("activities", help="list recent activities")
    activities.add_argument("--limit", type=positive_int, default=10)
    sync = commands.add_parser("sync", help="download and register activities")
    sync.add_argument("--since", type=iso_date, required=True)
    sync.add_argument("--until", type=iso_date)
    sync.add_argument("--data-dir", type=Path, default=Path("data"))
    parse = commands.add_parser("parse-swims", help="process pool swimming FIT files")
    parse.add_argument("--data-dir", type=Path, default=Path("data"))
    parse.add_argument("--force", action="store_true", help="reprocess existing sessions")
    preview = commands.add_parser(
        "workout-preview", help="validate and preview a swimming workout"
    )
    preview.add_argument("file", type=Path)
    workouts = commands.add_parser("workouts", help="list Garmin Connect workouts")
    workouts.add_argument("--limit", type=positive_int, default=20)
    workout = commands.add_parser("workout", help="show workout details")
    workout.add_argument("workout_id", type=positive_int)
    create = commands.add_parser(
        "workout-create", help="create a previously reviewed workout in Garmin"
    )
    create.add_argument("file", type=Path)
    create.add_argument("--confirm", action="store_true", help="confirm creation")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "login":
            login()
            print(f"Session saved to {token_store_path()}")
            return 0

        if args.command == "parse-swims":
            summary = parse_swims(args.data_dir, args.force)
            print(
                f"Processed: {summary.parsed} | "
                f"Existing: {summary.existing} | Failed: {summary.failed}"
            )
            return 1 if summary.failed else 0

        if args.command == "workout-preview":
            print(workout_preview(load_workout(args.file))["text"])
            return 0

        if args.command == "workout-create":
            workout = load_workout(args.file)
            if not args.confirm:
                raise ValueError(
                    "review the workout with `garmin workout-preview` and use --confirm"
                )
            print(
                json.dumps(
                    create_garmin_swim_workout(load_session(), workout),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        client = load_session()
        if args.command == "activities":
            activities = get_activities(client, args.limit)
            print(format_activities(activities))
            return 0

        if args.command == "workouts":
            print(format_garmin_workouts(list_garmin_workouts(client, args.limit)))
            return 0

        if args.command == "workout":
            print(
                json.dumps(
                    get_garmin_workout(client, args.workout_id),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        summary = sync_activities(
            client, args.since, args.until or date.today(), args.data_dir
        )
        print(
            f"Downloaded: {summary.downloaded} | "
            f"Existing: {summary.existing} | Failed: {summary.failed}"
        )
        parse_summary = parse_swims(args.data_dir)
        print(
            f"Swims processed: {parse_summary.parsed} | "
            f"Existing: {parse_summary.existing} | Failed: {parse_summary.failed}"
        )
        return 1 if summary.failed or parse_summary.failed else 0
    except (SessionNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
    except GarminConnectAuthenticationError:
        print(
            "Error: the session is invalid; run `garmin login` again.",
            file=sys.stderr,
        )
    except GarminConnectTooManyRequestsError:
        print(
            "Error: Garmin temporarily rate-limited requests; try again later.",
            file=sys.stderr,
        )
    except GarminConnectConnectionError as error:
        print(f"Garmin connection error: {error}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
    return 1
