import argparse
import sys

from isthisai.config import DB_PATH


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isthisai-enrich",
        description="Enrich collected data with derived metrics",
    )
    subparsers = parser.add_subparsers(dest="command", help="Enrichment step")

    subparsers.add_parser("subscribers", help="Fetch subscriber history")
    subparsers.add_parser("post-types", help="Classify posts by type")
    subparsers.add_parser("engagement", help="Compute engagement metrics")

    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help=f"Path to SQLite database (default: {DB_PATH})",
    )

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    print(f"isthisai-enrich: {args.command} command not yet implemented")
    print(f"  db_path={args.db_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
