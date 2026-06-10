#!/usr/bin/env python3
"""Build the aggregate-only, read-only deploy database for the live site.

The canonical DB (~3.8 GB) is too big to host and — more importantly — carries
verbatim comment text + usernames that Uncanny Atlas has no licence to republish
(see the plan's Part J / the About page). This script produces a small,
self-contained snapshot that is safe to serve publicly:

  1. snapshot the canonical DB with ``VACUUM INTO`` (a clean, defragmented copy in
     DELETE journal mode — no -wal/-shm siblings, consistent even if the source is
     mid-WAL);
  2. ``DROP TABLE comment_embeddings`` — the ~2.8 GB of 768-dim BLOBs, read by the
     web app only for a status COUNT(*), which is guarded to return 0 when absent —
     and ``DROP TABLE purge_tombstones`` — the takedown registry, which names the
     very people who asked to be removed and is only needed at insert time;
  3. strip PII / verbatim text from BOTH content tables:
     ``UPDATE comments SET body = NULL, author = NULL`` and
     ``UPDATE submissions SET author/title/selftext/permalink/url = NULL``
     (permalink and url embed the slugified title, so they go too).
     Every chart aggregates over created_utc / subreddit / link_id / score /
     is_video / is_self / flair + the comment_indicators join, so nothing visible
     changes; the public site shows no per-comment or per-post text anyway
     (read-only mode);
  4. ``VACUUM`` again to reclaim the freed pages.

Run it offline; never commit the output. Serve it with ISTHISAI_READONLY=1.

Usage:
    python scripts/build_deploy_db.py [--source PATH] [--output PATH] [--force]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def _mb(p: Path) -> float:
    return p.stat().st_size / (1024 * 1024) if p.exists() else 0.0


def build(source: Path, output: Path, force: bool) -> None:
    if not source.exists():
        sys.exit(f"Source database not found: {source}")
    if output.exists():
        if not force:
            sys.exit(f"Output already exists: {output} (use --force to overwrite)")
        output.unlink()
    # VACUUM INTO refuses to overwrite, so also clear any stale siblings.
    for sibling in (output.with_name(output.name + "-wal"), output.with_name(output.name + "-shm")):
        if sibling.exists():
            sibling.unlink()

    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Source : {source}  ({_mb(source):,.0f} MB)")
    print(f"Output : {output}")

    # 1. Clean, consistent snapshot (DELETE journal mode, fully checkpointed).
    print("[1/4] Snapshotting with VACUUM INTO ...")
    src = sqlite3.connect(source)
    try:
        src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        # VACUUM INTO takes a string expression; pass the path as a bound literal
        # via a quoted SQL string (escape embedded quotes).
        target = str(output).replace("'", "''")
        src.execute(f"VACUUM INTO '{target}'")
    finally:
        src.close()

    # 2-4. Strip embeddings + PII, then reclaim space.
    dst = sqlite3.connect(output)
    try:
        has_embeddings = dst.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='comment_embeddings'"
        ).fetchone()
        if has_embeddings:
            print("[2/4] Dropping comment_embeddings ...")
            dst.execute("DROP TABLE comment_embeddings")
        else:
            print("[2/4] comment_embeddings already absent; skipping.")
        # The takedown registry must NEVER ship: kind='author' rows name exactly the
        # people who asked to be removed. Tombstones are only consulted at insert
        # time in the canonical DB; the deploy DB takes no inserts.
        dst.execute("DROP TABLE IF EXISTS purge_tombstones")

        print("[3/4] Nulling comments.body/author + submissions text columns ...")
        dst.execute("UPDATE comments SET body = NULL, author = NULL")
        # permalink embeds the slugified TITLE and url duplicates it for self
        # posts, so both must go with title/selftext or the text survives in
        # recoverable form. No public chart reads either column.
        dst.execute(
            "UPDATE submissions SET author = NULL, title = NULL, selftext = NULL, "
            "permalink = NULL, url = NULL"
        )
        dst.commit()

        print("[4/4] VACUUM + journal_mode=DELETE ...")
        dst.execute("VACUUM")
        dst.execute("PRAGMA journal_mode = DELETE")

        # Sanity checks — BOTH content tables must be clean.
        leaked = dst.execute(
            "SELECT COUNT(*) FROM comments WHERE body IS NOT NULL OR author IS NOT NULL"
        ).fetchone()[0]
        leaked_subs = dst.execute(
            "SELECT COUNT(*) FROM submissions "
            "WHERE author IS NOT NULL OR title IS NOT NULL OR selftext IS NOT NULL "
            "OR permalink IS NOT NULL OR url IS NOT NULL"
        ).fetchone()[0]
        leaked_tombstones = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='purge_tombstones'"
        ).fetchone()[0]
        comments = dst.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        indicators = dst.execute("SELECT COUNT(*) FROM comment_indicators").fetchone()[0]
    finally:
        dst.close()

    if leaked:
        sys.exit(f"ERROR: {leaked} comment rows still carry body/author — aborting.")
    if leaked_subs:
        sys.exit(f"ERROR: {leaked_subs} submission rows still carry text/identity columns — aborting.")
    if leaked_tombstones:
        sys.exit("ERROR: purge_tombstones (the takedown registry) survived into the deploy DB — aborting.")

    print()
    print("Done. Aggregate-only deploy DB written.")
    print(f"  comments rows         : {comments:,}")
    print(f"  comment_indicators    : {indicators:,}")
    print(f"  comment text leaked   : {leaked} (must be 0)")
    print(f"  submission text leaked: {leaked_subs} (must be 0)")
    print(f"  output size           : {_mb(output):,.0f} MB  (was {_mb(source):,.0f} MB)")
    print()
    print("Serve it read-only:  ISTHISAI_DB_PATH=<output> ISTHISAI_READONLY=1 node web/build")
    print("Do NOT commit this file.")


def main() -> None:
    default_source = Path(os.environ.get("ISTHISAI_DB_PATH", str(Path("data") / "isthisai.db")))
    default_output = default_source.with_name("isthisai-deploy.db")

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=default_source, help=f"canonical DB (default: {default_source})")
    ap.add_argument("--output", type=Path, default=default_output, help=f"deploy DB to write (default: {default_output})")
    ap.add_argument("--force", action="store_true", help="overwrite an existing output file")
    args = ap.parse_args()

    build(args.source.resolve(), args.output.resolve(), args.force)


if __name__ == "__main__":
    main()
