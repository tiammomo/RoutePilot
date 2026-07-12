"""Command line interface for the RoutePilot V1 migration toolset."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .core import MigrationError, backfill, build_inventory, verify, write_json_atomic


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sessions-file", type=Path, help="Legacy sessions JSON snapshot.")
    parser.add_argument("--share-links-file", type=Path, help="Legacy share-links JSON snapshot.")
    parser.add_argument(
        "--source-database-url",
        default=os.getenv("ROUTEPILOT_LEGACY_DATABASE_URL", "").strip() or None,
        help="Read-only legacy SQLAlchemy URL. Defaults to ROUTEPILOT_LEGACY_DATABASE_URL.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.migration_v1",
        description="Fail-closed offline import of read-only RoutePilot V1 archives.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", help="Scan legacy data without writing it.")
    _add_source_arguments(inventory)
    inventory.add_argument("--owner-mapping", type=Path)
    inventory.add_argument("--file-data-root", type=Path, action="append", default=[])
    inventory.add_argument("--output", type=Path, required=True)

    migrate = subparsers.add_parser("backfill", help="Backfill deterministic ImportedTripArchive records.")
    _add_source_arguments(migrate)
    migrate.add_argument("--target-database-url", default=os.getenv("ROUTEPILOT_V1_DATABASE_URL", ""))
    migrate.add_argument("--inventory", type=Path, required=True)
    migrate.add_argument("--owner-mapping", type=Path, required=True)
    migrate.add_argument("--archive-manifest", type=Path, required=True)
    migrate.add_argument("--state", type=Path, required=True)
    migrate.add_argument("--batch-size", type=int, default=100)
    migrate.add_argument(
        "--apply",
        action="store_true",
        help="Actually insert into the expanded V1 schema. Without this flag the command is a dry-run.",
    )
    migrate.add_argument("--output", type=Path)

    reconcile = subparsers.add_parser("verify", help="Reconcile source, manifest, owners and target rows.")
    _add_source_arguments(reconcile)
    reconcile.add_argument("--target-database-url", default=os.getenv("ROUTEPILOT_V1_DATABASE_URL", ""))
    reconcile.add_argument("--inventory", type=Path, required=True)
    reconcile.add_argument("--owner-mapping", type=Path, required=True)
    reconcile.add_argument("--archive-manifest", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    return parser


def _source_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "sessions_file": args.sessions_file,
        "share_links_file": args.share_links_file,
        "source_database_url": args.source_database_url,
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], Path | None]:
    if args.command == "inventory":
        report = build_inventory(
            **_source_kwargs(args),
            owner_mapping_file=args.owner_mapping,
            file_data_roots=args.file_data_root,
        )
        return report, args.output
    if args.command == "backfill":
        report = backfill(
            **_source_kwargs(args),
            target_database_url=args.target_database_url,
            inventory_file=args.inventory,
            owner_mapping_file=args.owner_mapping,
            archive_manifest_file=args.archive_manifest,
            state_file=args.state,
            batch_size=args.batch_size,
            dry_run=not args.apply,
        )
        return report, args.output
    if args.command == "verify":
        report = verify(
            **_source_kwargs(args),
            target_database_url=args.target_database_url,
            inventory_file=args.inventory,
            owner_mapping_file=args.owner_mapping,
            archive_manifest_file=args.archive_manifest,
        )
        return report, args.output
    raise MigrationError("unsupported offline migration command")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report, output = run(args)
        if output is not None:
            write_json_atomic(output, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if args.command == "verify" and not report.get("passed", False):
            return 2
        return 0
    except MigrationError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception:
        # Do not print driver errors: they can include database hosts, usernames,
        # query values, or other deployment details.  Operators should correlate
        # the non-zero exit with restricted platform diagnostics.
        print(
            json.dumps(
                {"status": "blocked", "error": "unexpected migration failure; inspect secure diagnostics"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
