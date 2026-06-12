import argparse
import json
from collections.abc import Sequence

from maildrop.config import get_settings
from maildrop.db import create_engine_from_url, make_session_factory
from maildrop.repository import cleanup_old_messages


def cleanup_command(*, dry_run: bool) -> int:
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    session_factory = make_session_factory(engine)
    with session_factory() as db:
        result = cleanup_old_messages(
            db,
            message_retention_days=settings.message_retention_days,
            unassigned_retention_days=settings.unassigned_retention_days,
            dry_run=dry_run,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maildrop")
    subparsers = parser.add_subparsers(dest="command", required=True)
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Delete messages older than configured retention windows.",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without deleting rows.",
    )
    args = parser.parse_args(argv)

    if args.command == "cleanup":
        return cleanup_command(dry_run=args.dry_run)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
