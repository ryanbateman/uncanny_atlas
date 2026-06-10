import argparse
import sys

from isthisai.config import DB_PATH
from isthisai.db import create_tables, get_connection
from isthisai.media import classify_media_type


def reclassify_post_types(conn) -> int:
    """Recompute submissions.media_type for every row.

    The classification rules live in isthisai.media (host/extension lists);
    when they change — a new video host appears, say — this re-applies them in
    place without needing a schema-version bump. Returns rows changed.
    """
    rows = conn.execute("SELECT id, is_video, is_self, url, media_type FROM submissions").fetchall()
    changes = [
        (new, sid)
        for sid, iv, isf, url, old in rows
        if (new := classify_media_type(iv, isf, url)) != old
    ]
    conn.executemany("UPDATE submissions SET media_type = ? WHERE id = ?", changes)
    conn.commit()
    return len(changes)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isthisai-enrich",
        description="Enrich collected data with derived metrics",
    )
    subparsers = parser.add_subparsers(dest="command", help="Enrichment step")

    subparsers.add_parser("subscribers", help="Fetch subscriber history")
    subparsers.add_parser(
        "post-types",
        help="(Re)classify submissions.media_type from the rules in isthisai.media",
    )
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

    if args.command == "post-types":
        conn = get_connection(args.db_path)
        create_tables(conn)  # idempotent; ensures the v10 column exists
        try:
            total = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
            changed = reclassify_post_types(conn)
            counts = conn.execute(
                "SELECT media_type, COUNT(*) FROM submissions GROUP BY media_type ORDER BY 2 DESC"
            ).fetchall()
        finally:
            conn.close()
        print(f"Reclassified {total:,} submissions; {changed:,} changed.")
        for media, count in counts:
            print(f"  {media}: {count:,}")
        return

    print(f"isthisai-enrich: {args.command} command not yet implemented")
    print(f"  db_path={args.db_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
