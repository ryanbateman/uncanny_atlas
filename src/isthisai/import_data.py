import argparse
import io
import json
import logging
import signal
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import requests

from isthisai.config import (
    DB_PATH,
    DEFAULT_SUBREDDIT,
    INITIAL_RETRY_DELAY,
    MAX_RETRIES,
    MAX_RETRY_DELAY,
    REQUEST_TIMEOUT,
)
from isthisai.db import create_tables, get_connection, insert_comments, insert_submissions

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({"User-Agent": "isthisai-explorer/0.1.0"})

_shutdown = False


def _handle_signal(signum: int, frame: Any) -> None:
    global _shutdown
    logger.info("Received signal %s, shutting down gracefully...", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

ARCTIC_SHIFT_BASE_URL = "https://arctic-shift.photon-reddit.com/api"


def _normalize_submission(raw: dict[str, Any]) -> dict[str, Any]:
    created = raw.get("created_utc", 0)
    if isinstance(created, float):
        created = int(created)

    is_video = raw.get("is_video", False)
    is_self = raw.get("is_self", False)

    upvote_ratio = raw.get("upvote_ratio")
    if isinstance(upvote_ratio, int):
        upvote_ratio = float(upvote_ratio)

    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "author": raw.get("author"),
        "created_utc": created,
        "score": raw.get("score"),
        "num_comments": raw.get("num_comments"),
        "upvote_ratio": upvote_ratio,
        "link_flair_text": raw.get("link_flair_text"),
        "is_video": int(is_video) if is_video is not None else None,
        "is_self": int(is_self) if is_self is not None else None,
        "url": raw.get("url"),
        "selftext": raw.get("selftext"),
        "permalink": raw.get("permalink"),
    }


def _normalize_comment(raw: dict[str, Any]) -> dict[str, Any]:
    created = raw.get("created_utc", 0)
    if isinstance(created, float):
        created = int(created)

    link_id = raw.get("link_id", "")
    parent_id = raw.get("parent_id", "")

    if link_id.startswith("t3_"):
        link_id = link_id[3:]
    if parent_id.startswith(("t1_", "t3_")):
        parent_id = parent_id[3:]

    return {
        "id": raw.get("id"),
        "link_id": link_id,
        "author": raw.get("author"),
        "body": raw.get("body"),
        "created_utc": created,
        "score": raw.get("score"),
        "parent_id": parent_id,
    }


def _fetch_page_arctic(
    endpoint: str,
    params: dict[str, Any],
) -> list[dict[str, Any]] | None:
    url = f"{ARCTIC_SHIFT_BASE_URL}{endpoint}"
    retry_delay = INITIAL_RETRY_DELAY

    for attempt in range(MAX_RETRIES):
        if _shutdown:
            return None

        try:
            resp = _session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                logger.warning("Rate limited (429), retrying in %.1fs...", retry_delay)
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                continue
            if resp.status_code in (502, 503, 504):
                logger.warning(
                    "Server error %d, retrying in %.1fs...", resp.status_code, retry_delay
                )
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                continue
            if resp.status_code == 400:
                logger.error("Bad request (400): %s", resp.text[:500])
                return None
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except requests.exceptions.Timeout:
            logger.warning("Timeout on attempt %d/%d", attempt + 1, MAX_RETRIES)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        except requests.exceptions.RequestException as e:
            logger.error("Request error: %s", e)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)

    logger.error("Exhausted all %d retries for %s", MAX_RETRIES, url)
    return None


def import_from_arctic_shift(
    conn: sqlite3.Connection,
    data_type: str,
    subreddit: str = DEFAULT_SUBREDDIT,
    after: str | None = None,
    before: str | None = None,
    delay: float = 2.0,
) -> int:
    if data_type == "submissions":
        endpoint = "/posts/search"
        normalize = _normalize_submission
        insert_fn = insert_submissions
    elif data_type == "comments":
        endpoint = "/comments/search"
        normalize = _normalize_comment
        insert_fn = insert_comments
    else:
        logger.error("Unknown data type: %s", data_type)
        return 0

    total_fetched = 0
    last_id: str | None = None

    logger.info("Starting Arctic Shift import of r/%s %s", subreddit, data_type)

    while not _shutdown:
        params: dict[str, Any] = {
            "subreddit": subreddit,
            "limit": 100,
            "sort": "asc",
        }
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if last_id:
            params["after"] = last_id

        items = _fetch_page_arctic(endpoint, params)
        if items is None:
            logger.error("Failed to fetch page, stopping")
            break

        if not items:
            logger.info("No more %s to fetch", data_type)
            break

        normalized = [normalize(item) for item in items]
        insert_fn(conn, normalized, subreddit=subreddit)
        total_fetched += len(items)

        logger.info(
            "Fetched %d %s (total: %d, last: %s)",
            len(items),
            data_type,
            total_fetched,
            items[-1].get("id"),
        )

        created_utc = items[-1].get("created_utc")
        if created_utc:
            if isinstance(created_utc, float):
                created_utc = int(created_utc)
            last_id = str(created_utc)

        if len(items) < 100:
            logger.info("Received fewer than limit (%d), collection complete", len(items))
            break

        time.sleep(delay)

    logger.info("Finished: fetched %d total %s", total_fetched, data_type)
    return total_fetched


def import_from_file(
    conn: sqlite3.Connection,
    file_path: Path,
    data_type: str,
    subreddit: str = DEFAULT_SUBREDDIT,
    subreddit_filter: str | None = None,
) -> int:
    try:
        import zstandard
    except ImportError:
        logger.error("zstandard required. Install with: pip install isthisai[import]")
        return 0

    if data_type == "submissions":
        normalize = _normalize_submission
        insert_fn = insert_submissions
    elif data_type == "comments":
        normalize = _normalize_comment
        insert_fn = insert_comments
    else:
        logger.error("Unknown data type: %s", data_type)
        return 0

    total_imported = 0
    batch: list[dict[str, Any]] = []
    batch_size = 1000

    logger.info("Importing %s from %s", data_type, file_path)

    dctx = zstandard.ZstdDecompressor()
    with open(file_path, "rb") as f:
        stream_reader = dctx.stream_reader(f)
        text_stream = io.TextIOWrapper(stream_reader, encoding="utf-8")

        for line_num, line in enumerate(text_stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON at line %d", line_num)
                continue

            if subreddit_filter and raw.get("subreddit", "").lower() != subreddit_filter.lower():
                continue

            normalized = normalize(raw)
            batch.append(normalized)

            if len(batch) >= batch_size:
                insert_fn(conn, batch, subreddit=subreddit)
                total_imported += len(batch)
                logger.info("Imported %d %s (total: %d)", len(batch), data_type, total_imported)
                batch = []

    if batch:
        insert_fn(conn, batch, subreddit=subreddit)
        total_imported += len(batch)

    logger.info("Finished: imported %d total %s", total_imported, data_type)
    return total_imported


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isthisai-import",
        description="Import data from Arctic Shift API or NDJSON (.zst) files",
    )
    subparsers = parser.add_subparsers(dest="command", help="Import source")

    api_parser = subparsers.add_parser("api", help="Import from Arctic Shift API")
    api_parser.add_argument(
        "datatype", choices=["submissions", "comments"], help="Data type to import"
    )
    api_parser.add_argument("--subreddit", default=DEFAULT_SUBREDDIT)
    api_parser.add_argument("--after", help="Start date (YYYY-MM-DD or epoch)")
    api_parser.add_argument("--before", help="End date (YYYY-MM-DD or epoch)")
    api_parser.add_argument("--db-path", default=str(DB_PATH))
    api_parser.add_argument("-v", "--verbose", action="store_true")

    file_parser = subparsers.add_parser("file", help="Import from Arctic Shift .zst dump file")
    file_parser.add_argument(
        "datatype", choices=["submissions", "comments"], help="Data type to import"
    )
    file_parser.add_argument("path", type=Path, help="Path to .zst file")
    file_parser.add_argument("--subreddit", default=DEFAULT_SUBREDDIT)
    file_parser.add_argument("--subreddit-filter", help="Only import rows for this subreddit")
    file_parser.add_argument("--db-path", default=str(DB_PATH))
    file_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    db_path = Path(args.db_path)
    conn = get_connection(db_path)
    create_tables(conn)

    try:
        if args.command == "api":
            total = import_from_arctic_shift(
                conn,
                data_type=args.datatype,
                subreddit=args.subreddit,
                after=args.after,
                before=args.before,
            )
            print(f"Imported {total} {args.datatype} from Arctic Shift API")
        elif args.command == "file":
            total = import_from_file(
                conn,
                file_path=args.path,
                data_type=args.datatype,
                subreddit=args.subreddit,
                subreddit_filter=args.subreddit_filter,
            )
            print(f"Imported {total} {args.datatype} from file")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
