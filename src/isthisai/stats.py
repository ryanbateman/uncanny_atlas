import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from isthisai.config import DB_PATH, DEFAULT_SUBREDDIT
from isthisai.db import create_tables, get_connection


def _build_where(conditions: list[tuple[str, str]]) -> tuple[str, list[str]]:
    parts = []
    params = []
    for clause, param in conditions:
        if param is not None:
            parts.append(clause)
            params.append(param)
    if parts:
        return "WHERE " + " AND ".join(parts), params
    return "", []


def _sub_conditions(subreddit: str | None) -> list[tuple[str, str | None]]:
    if subreddit:
        return [("subreddit = ?", subreddit)]
    return []


def compute_stats(conn: sqlite3.Connection, subreddit: str | None = None) -> dict[str, Any]:
    stats: dict[str, Any] = {}

    sub_where, sub_params = _build_where(_sub_conditions(subreddit))
    com_where, com_params = _build_where(_sub_conditions(subreddit))

    sub_count = conn.execute(
        f"SELECT COUNT(*) FROM submissions {sub_where}", sub_params
    ).fetchone()[0]
    com_count = conn.execute(f"SELECT COUNT(*) FROM comments {com_where}", com_params).fetchone()[0]
    stats["total_submissions"] = sub_count
    stats["total_comments"] = com_count

    if sub_count > 0:
        sub_range = conn.execute(
            f"SELECT MIN(created_utc), MAX(created_utc) FROM submissions {sub_where}", sub_params
        ).fetchone()
        stats["submission_date_range"] = {
            "min": sub_range[0],
            "min_iso": datetime.fromtimestamp(sub_range[0], tz=timezone.utc).isoformat()
            if sub_range[0]
            else None,
            "max": sub_range[1],
            "max_iso": datetime.fromtimestamp(sub_range[1], tz=timezone.utc).isoformat()
            if sub_range[1]
            else None,
        }
    else:
        stats["submission_date_range"] = None

    if com_count > 0:
        com_range = conn.execute(
            f"SELECT MIN(created_utc), MAX(created_utc) FROM comments {com_where}", com_params
        ).fetchone()
        stats["comment_date_range"] = {
            "min": com_range[0],
            "min_iso": datetime.fromtimestamp(com_range[0], tz=timezone.utc).isoformat()
            if com_range[0]
            else None,
            "max": com_range[1],
            "max_iso": datetime.fromtimestamp(com_range[1], tz=timezone.utc).isoformat()
            if com_range[1]
            else None,
        }
    else:
        stats["comment_date_range"] = None

    not_null_where, not_null_params = _build_where(
        _sub_conditions(subreddit) + [("author IS NOT NULL", None)]
    )
    stats["unique_submitters"] = conn.execute(
        f"SELECT COUNT(DISTINCT author) FROM submissions {not_null_where}", not_null_params
    ).fetchone()[0]
    stats["unique_commenters"] = conn.execute(
        f"SELECT COUNT(DISTINCT author) FROM comments {not_null_where}", not_null_params
    ).fetchone()[0]

    if sub_count > 0:
        stats["avg_comments_per_submission"] = round(com_count / sub_count, 1)
    else:
        stats["avg_comments_per_submission"] = 0.0

    stats["top_submitters"] = [
        {"author": row[0], "count": row[1]}
        for row in conn.execute(
            f"SELECT author, COUNT(*) as c FROM submissions {not_null_where} "
            f"GROUP BY author ORDER BY c DESC LIMIT 10",
            not_null_params,
        ).fetchall()
    ]

    flair_rows = conn.execute(
        f"SELECT COALESCE(link_flair_text, '(none)'), COUNT(*) FROM submissions {sub_where} "
        f"GROUP BY link_flair_text ORDER BY COUNT(*) DESC",
        sub_params,
    ).fetchall()
    stats["flair_distribution"] = [{"flair": row[0], "count": row[1]} for row in flair_rows]

    if sub_count > 0:
        stats["submissions_per_month"] = [
            {"month": row[0], "count": row[1]}
            for row in conn.execute(
                f"SELECT strftime('%Y-%m', created_utc, 'unixepoch') as month, "
                f"COUNT(*) as c FROM submissions {sub_where} GROUP BY month ORDER BY month",
                sub_params,
            ).fetchall()
        ]
    else:
        stats["submissions_per_month"] = []

    return stats


def compute_gaps(conn: sqlite3.Connection, subreddit: str | None = None) -> list[dict[str, Any]]:
    sub_where, sub_params = _build_where(_sub_conditions(subreddit))
    sub_count = conn.execute(
        f"SELECT COUNT(*) FROM submissions {sub_where}", sub_params
    ).fetchone()[0]
    if sub_count == 0:
        return []

    date_range = conn.execute(
        f"SELECT MIN(created_utc), MAX(created_utc) FROM submissions {sub_where}", sub_params
    ).fetchone()
    if not date_range[0] or not date_range[1]:
        return []

    min_date = datetime.fromtimestamp(date_range[0], tz=timezone.utc).date()
    max_date = datetime.fromtimestamp(date_range[1], tz=timezone.utc).date()

    active_days = {
        row[0]
        for row in conn.execute(
            f"SELECT DATE(created_utc, 'unixepoch') FROM submissions {sub_where}", sub_params
        ).fetchall()
        if row[0]
    }

    gaps = []
    gap_start = None

    for i in range((max_date - min_date).days + 1):
        day = min_date + timedelta(days=i)
        day_str = day.isoformat()

        if day_str in active_days:
            if gap_start is not None:
                prev_day = (day - timedelta(days=1)).isoformat()
                length = (day - datetime.fromisoformat(gap_start).date()).days
                if length >= 1:
                    gaps.append(
                        {
                            "start": gap_start,
                            "end": prev_day,
                            "days": length,
                        }
                    )
                gap_start = None
        else:
            prev_day = (day - timedelta(days=1)).isoformat()
            if gap_start is None and prev_day in active_days:
                gap_start = day_str

    if gap_start is not None:
        end_date = max_date
        length = (end_date - datetime.fromisoformat(gap_start).date()).days + 1
        gaps.append(
            {
                "start": gap_start,
                "end": end_date.isoformat(),
                "days": length,
            }
        )

    return gaps


def print_stats(stats: dict[str, Any]) -> None:
    dr = stats.get("submission_date_range")
    cr = stats.get("comment_date_range")

    print("=" * 60)
    print("  Uncanny Atlas — Data Summary")
    print("=" * 60)
    print(f"  Submissions:       {stats['total_submissions']:,}")
    print(f"  Comments:          {stats['total_comments']:,}")
    if dr:
        print(f"  Submission range:   {dr['min_iso'][:10]} to {dr['max_iso'][:10]}")
    else:
        print("  Submission range:   (no data)")
    if cr:
        print(f"  Comment range:      {cr['min_iso'][:10]} to {cr['max_iso'][:10]}")
    else:
        print("  Comment range:      (no data)")
    print(f"  Unique submitters:  {stats['unique_submitters']:,}")
    print(f"  Unique commenters:  {stats['unique_commenters']:,}")
    print(f"  Avg comments/post:  {stats['avg_comments_per_submission']}")

    if stats["flair_distribution"]:
        print()
        print("  Flair distribution:")
        for item in stats["flair_distribution"]:
            print(f"    {item['flair']:20s} {item['count']:>6d}")

    if stats["top_submitters"]:
        print()
        print("  Top submitters:")
        for item in stats["top_submitters"]:
            print(f"    {item['author']:20s} {item['count']:>6d} posts")

    if stats.get("submissions_per_month"):
        print()
        print("  Submissions per month:")
        max_count = max(item["count"] for item in stats["submissions_per_month"])
        max_bar = 40
        for item in stats["submissions_per_month"]:
            bar_len = round(item["count"] / max_count * max_bar) if max_count else 0
            bar = "#" * bar_len
            print(f"    {item['month']}  {item['count']:>5d}  {bar}")

    print("=" * 60)


def print_gaps(gaps: list[dict[str, Any]]) -> None:
    if not gaps:
        print("No data gaps detected (single-day gaps between active days).")
        return

    print(f"Found {len(gaps)} data gap(s) between active days:")
    print()
    for gap in gaps:
        print(f"  {gap['start']} to {gap['end']} ({gap['days']} day(s))")
    print()


def print_sample(conn: sqlite3.Connection, subreddit: str | None = None, n: int = 5) -> None:
    sub_where, sub_params = _build_where(_sub_conditions(subreddit))
    com_where, com_params = _build_where(_sub_conditions(subreddit))
    print("=== Recent Submissions ===")
    rows = conn.execute(
        f"SELECT created_utc, title, author, score, num_comments "
        f"FROM submissions {sub_where} ORDER BY created_utc DESC LIMIT ?",
        sub_params + [n],
    ).fetchall()
    if not rows:
        print("  (no submissions)")
    for row in rows:
        date = datetime.fromtimestamp(row[0], tz=timezone.utc).strftime("%Y-%m-%d")
        title = (row[1] or "")[:60]
        author = row[2] or "[deleted]"
        print(f'  [{date}] "{title}" by {author} (score: {row[3]}, {row[4]} comments)')

    print()
    print("=== Recent Comments ===")
    rows = conn.execute(
        f"SELECT created_utc, body, author, score FROM comments {com_where} ORDER BY created_utc DESC LIMIT ?",
        com_params + [n],
    ).fetchall()
    if not rows:
        print("  (no comments)")
    for row in rows:
        date = datetime.fromtimestamp(row[0], tz=timezone.utc).strftime("%Y-%m-%d")
        body = (row[1] or "")[:70].replace("\n", " ")
        author = row[2] or "[deleted]"
        print(f'  [{date}] "{body}" by {author} (score: {row[3]})')


def write_stats(stats: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(stats, f, indent=2, default=str)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isthisai-stats",
        description="Print summary statistics about collected data",
    )
    subparsers = parser.add_subparsers(dest="command", help="What to show")

    subparsers.add_parser("summary", help="Full summary report (default)")
    subparsers.add_parser("gaps", help="Detect data gaps between active days")
    subparsers.add_parser("sample", help="Show recent posts and comments")

    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help=f"Path to SQLite database (default: {DB_PATH})",
    )
    parser.add_argument(
        "--subreddit",
        default=None,
        help=f"Filter by subreddit (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also write stats to data/stats_report.json",
    )

    args = parser.parse_args(argv)
    command = args.command or "summary"

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"No database found at {db_path}")
        print("Run isthisai-collect to populate the database first.")
        sys.exit(1)

    conn = get_connection(db_path)
    create_tables(conn)

    try:
        if command == "summary":
            stats = compute_stats(conn, subreddit=args.subreddit)
            print_stats(stats)
            if args.json:
                write_stats(stats, db_path.parent / "stats_report.json")
                print(f"\nStats written to {db_path.parent / 'stats_report.json'}")
        elif command == "gaps":
            gaps = compute_gaps(conn, subreddit=args.subreddit)
            print_gaps(gaps)
        elif command == "sample":
            print_sample(conn, subreddit=args.subreddit)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
