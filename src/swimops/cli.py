from __future__ import annotations

import argparse
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
from swimops.sync import sync_activities


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("debe ser mayor que cero")
    return number


def iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("debe tener formato YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("debe tener formato YYYY-MM-DD")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="garmin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="inicia sesión y guarda los tokens localmente")
    activities = commands.add_parser("activities", help="lista actividades recientes")
    activities.add_argument("--limit", type=positive_int, default=10)
    sync = commands.add_parser("sync", help="descarga y registra actividades")
    sync.add_argument("--since", type=iso_date, required=True)
    sync.add_argument("--until", type=iso_date)
    sync.add_argument("--data-dir", type=Path, default=Path("data"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "login":
            login()
            print(f"Sesión guardada en {token_store_path()}")
            return 0

        client = load_session()
        if args.command == "activities":
            activities = get_activities(client, args.limit)
            print(format_activities(activities))
            return 0

        summary = sync_activities(
            client, args.since, args.until or date.today(), args.data_dir
        )
        print(
            f"Descargadas: {summary.downloaded} | "
            f"Existentes: {summary.existing} | Fallidas: {summary.failed}"
        )
        return 1 if summary.failed else 0
    except (SessionNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
    except GarminConnectAuthenticationError:
        print(
            "Error: la sesión no es válida; ejecuta `garmin login` de nuevo.",
            file=sys.stderr,
        )
    except GarminConnectTooManyRequestsError:
        print(
            "Error: Garmin limitó temporalmente las solicitudes; inténtalo más tarde.",
            file=sys.stderr,
        )
    except GarminConnectConnectionError as error:
        print(f"Error de conexión con Garmin: {error}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
    return 1
