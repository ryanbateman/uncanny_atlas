"""Takedown tool: permanently purge content from the local database.

Collection (collect.py / import_data.py) uses INSERT OR IGNORE against
append-only archives, so deleting a row on its own is NOT a takedown — the next
collect/import run would quietly re-insert it. This tool deletes the content
AND writes tombstones (purge_tombstones, schema v8) that the insert paths in
db.py check, so a purge survives every future re-collection.

What each kind removes:
  comment <id>       the comment row, its comment_indicators rows, and its
                     comment_embeddings row (when the table is present).
  submission <id>    the submission row and every comment under it (both bare
                     and t3_-prefixed link_id forms), with the same cascades.
  author <username>  every comment and submission by that author (matched
                     case-insensitively), with the same cascades. The author's
                     submissions AND each removed comment id are tombstoned
                     individually, so the content stays gone even if a future
                     archive snapshot carries it under '[deleted]' or a
                     different casing. Other users' existing comments under the
                     author's submissions are left in place, but the tombstoned
                     submissions no longer accept newly collected comments.

Dry-run by default: prints what would be removed. Pass --yes to execute.
After purging, rebuild the deploy DB / static site so the public artifact
reflects the removal. (build_deploy_db.py drops the tombstone table itself —
the takedown registry never ships.)

Usage:
    isthisai-purge comment abc123 [--yes]
    isthisai-purge submission 135gmrp [--yes]
    isthisai-purge author some_username [--yes]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from isthisai.config import DB_PATH
from isthisai.db import create_tables, get_connection

# SQLite's bound-parameter cap is 32,766 (3.32+); stay far below it so even a
# bot-scale author purge (tens of thousands of comments) works in dry-run too.
_CHUNK = 5000


def _chunks(seq: list[str], n: int = _CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _normalize_ident(kind: str, ident: str) -> str:
    # Reddit fullname prefixes (t3_ submission, t1_ comment) are stored
    # inconsistently in the wild; ids in this DB are bare. Accepting a prefixed
    # id unnormalized would purge only one link_id form and write a tombstone
    # the insert filter can never match — a silent half-takedown.
    for prefix in ("t3_", "t1_"):
        if ident.startswith(prefix):
            return ident[len(prefix) :]
    return ident


def _count_in(conn: sqlite3.Connection, sql_tpl: str, ids: list[str]) -> int:
    total = 0
    for chunk in _chunks(ids):
        ph = ",".join("?" * len(chunk))
        total += conn.execute(sql_tpl.format(ph=ph), chunk).fetchone()[0]
    return total


def _delete_in(conn: sqlite3.Connection, sql_tpl: str, ids: list[str]) -> None:
    for chunk in _chunks(ids):
        ph = ",".join("?" * len(chunk))
        conn.execute(sql_tpl.format(ph=ph), chunk)


def _affected(conn: sqlite3.Connection, kind: str, ident: str) -> dict[str, list[str]]:
    """Resolve the comment ids / submission ids a purge would remove."""
    if kind == "comment":
        comment_ids = [
            r[0] for r in conn.execute("SELECT id FROM comments WHERE id = ?", (ident,))
        ]
        submission_ids: list[str] = []
    elif kind == "submission":
        submission_ids = [
            r[0] for r in conn.execute("SELECT id FROM submissions WHERE id = ?", (ident,))
        ]
        # link_id is stored both bare and t3_-prefixed depending on the source.
        comment_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM comments WHERE link_id = ? OR link_id = ?",
                (ident, f"t3_{ident}"),
            )
        ]
    elif kind == "author":
        # Case-insensitive: author casing varies across archive sources.
        comment_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM comments WHERE author = ? COLLATE NOCASE", (ident,)
            )
        ]
        submission_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM submissions WHERE author = ? COLLATE NOCASE", (ident,)
            )
        ]
    else:  # pragma: no cover - argparse restricts choices
        raise ValueError(f"unknown kind: {kind}")
    return {"comments": comment_ids, "submissions": submission_ids}


def purge(conn: sqlite3.Connection, kind: str, ident: str, execute: bool) -> None:
    ident = _normalize_ident(kind, ident) if kind != "author" else ident
    found = _affected(conn, kind, ident)
    comment_ids = found["comments"]
    submission_ids = found["submissions"]

    has_embeddings = _table_exists(conn, "comment_embeddings")
    n_indicators = 0
    n_embeddings = 0
    if comment_ids:
        n_indicators = _count_in(
            conn, "SELECT COUNT(*) FROM comment_indicators WHERE comment_id IN ({ph})", comment_ids
        )
        if has_embeddings:
            n_embeddings = _count_in(
                conn,
                "SELECT COUNT(*) FROM comment_embeddings WHERE comment_id IN ({ph})",
                comment_ids,
            )

    print(f"Purge {kind} {ident!r}:")
    print(f"  comments            : {len(comment_ids)}")
    print(f"  submissions         : {len(submission_ids)}")
    print(f"  comment_indicators  : {n_indicators}")
    print(f"  comment_embeddings  : {n_embeddings}")

    if not comment_ids and not submission_ids:
        print("Nothing found — id/username not in the database.")
        print("(Executing still writes a tombstone, so it can never be imported in future.)")

    if not execute:
        print("\nDRY RUN — nothing deleted. Re-run with --yes to execute.")
        return

    with conn:  # single transaction
        if comment_ids:
            _delete_in(
                conn, "DELETE FROM comment_indicators WHERE comment_id IN ({ph})", comment_ids
            )
            if has_embeddings:
                _delete_in(
                    conn, "DELETE FROM comment_embeddings WHERE comment_id IN ({ph})", comment_ids
                )
            _delete_in(conn, "DELETE FROM comments WHERE id IN ({ph})", comment_ids)
        if submission_ids:
            _delete_in(conn, "DELETE FROM submissions WHERE id IN ({ph})", submission_ids)

        # Tombstones: the purged identity itself, plus — for author purges —
        # their submissions AND every removed comment id, so the content stays
        # gone even if a future archive snapshot carries the same rows under
        # '[deleted]' or a different author casing.
        conn.execute(
            "INSERT OR IGNORE INTO purge_tombstones (kind, id) VALUES (?, ?)", (kind, ident)
        )
        if kind == "author":
            for sid in submission_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO purge_tombstones (kind, id) VALUES ('submission', ?)",
                    (sid,),
                )
            for chunk in _chunks(comment_ids):
                conn.executemany(
                    "INSERT OR IGNORE INTO purge_tombstones (kind, id) VALUES ('comment', ?)",
                    [(cid,) for cid in chunk],
                )

    print("\nPurged and tombstoned. This content cannot be re-imported by future collection.")
    print("Remember to rebuild the deploy DB / static site so the public artifact updates.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("kind", choices=["comment", "submission", "author"])
    ap.add_argument("id", help="comment id, submission id, or username (t3_/t1_ prefixes ok)")
    ap.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument(
        "--db-path", type=Path, default=None, help=f"database path (default: {DB_PATH})"
    )
    args = ap.parse_args()

    db_path = args.db_path or DB_PATH
    # Unlike the collectors, a purge tool must never create a database: running
    # from the wrong directory would tombstone a throwaway file while the real
    # DB keeps the content — a takedown the operator believes happened.
    if not Path(db_path).exists():
        sys.exit(f"Database not found: {db_path} (pass --db-path; refusing to create one)")

    conn = get_connection(db_path)
    create_tables(conn)  # idempotent; ensures the v8 tombstone table exists
    try:
        purge(conn, args.kind, args.id, execute=args.yes)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
