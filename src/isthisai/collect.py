import argparse
import logging
import signal
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
    PULLPUSH_BASE_URL,
    PULLPUSH_DELAY_SECONDS,
    PULLPUSH_PAGE_SIZE,
    REQUEST_TIMEOUT,
)
from isthisai.db import (
    create_tables,
    get_connection,
    get_metadata,
    insert_comments,
    insert_submissions,
    set_metadata,
)

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


def _fetch_page(
    endpoint: str,
    params: dict[str, Any],
) -> list[dict[str, Any]] | None:
    url = f"{PULLPUSH_BASE_URL}{endpoint}"
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


def fetch_submissions(
    conn: Any,
    subreddit: str = DEFAULT_SUBREDDIT,
    full_refresh: bool = False,
) -> int:
    total_fetched = 0
    after_ts: float | None = None

    if not full_refresh:
        stored = get_metadata(conn, f"last_submission_utc_{subreddit}")
        if stored:
            after_ts = float(stored)
            logger.info("Resuming from stored progress: after=%s", after_ts)

    if after_ts is None:
        logger.info("Starting full collection of r/%s submissions", subreddit)
    else:
        logger.info("Collecting r/%s submissions after timestamp %s", subreddit, after_ts)

    while not _shutdown:
        params: dict[str, Any] = {
            "subreddit": subreddit,
            "size": PULLPUSH_PAGE_SIZE,
            "sort": "asc",
            "sort_type": "created_utc",
        }
        if after_ts is not None:
            params["after"] = int(after_ts) + 1

        items = _fetch_page("/reddit/search/submission/", params)
        if items is None:
            logger.error("Failed to fetch page, stopping")
            break

        if not items:
            logger.info("No more submissions to fetch")
            break

        insert_submissions(conn, items, subreddit=subreddit)
        total_fetched += len(items)

        logger.info(
            "Fetched %d submissions (total: %d, last: %s)",
            len(items),
            total_fetched,
            items[-1].get("id"),
        )

        last_utc = items[-1].get("created_utc")
        if last_utc:
            after_ts = last_utc
            set_metadata(conn, f"last_submission_utc_{subreddit}", str(after_ts))

        time.sleep(PULLPUSH_DELAY_SECONDS)

    logger.info("Finished: fetched %d total submissions", total_fetched)
    return total_fetched


def fetch_comments(
    conn: Any,
    subreddit: str = DEFAULT_SUBREDDIT,
    full_refresh: bool = False,
) -> int:
    total_fetched = 0
    after_ts: float | None = None

    if not full_refresh:
        stored = get_metadata(conn, f"last_comment_utc_{subreddit}")
        if stored:
            after_ts = float(stored)
            logger.info("Resuming from stored progress: after=%s", after_ts)

    if after_ts is None:
        logger.info("Starting full collection of r/%s comments", subreddit)
    else:
        logger.info("Collecting r/%s comments after timestamp %s", subreddit, after_ts)

    while not _shutdown:
        params: dict[str, Any] = {
            "subreddit": subreddit,
            "size": PULLPUSH_PAGE_SIZE,
            "sort": "asc",
            "sort_type": "created_utc",
        }
        if after_ts is not None:
            params["after"] = int(after_ts) + 1

        items = _fetch_page("/reddit/search/comment/", params)
        if items is None:
            logger.error("Failed to fetch page, stopping")
            break

        if not items:
            logger.info("No more comments to fetch")
            break

        insert_comments(conn, items, subreddit=subreddit)
        total_fetched += len(items)

        logger.info(
            "Fetched %d comments (total: %d, last: %s)",
            len(items),
            total_fetched,
            items[-1].get("id"),
        )

        last_utc = items[-1].get("created_utc")
        if last_utc:
            after_ts = last_utc
            set_metadata(conn, f"last_comment_utc_{subreddit}", str(after_ts))

        time.sleep(PULLPUSH_DELAY_SECONDS)

    logger.info("Finished: fetched %d total comments", total_fetched)
    return total_fetched


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isthisai-collect",
        description="Collect submission and comment data from PullPush API",
    )
    subparsers = parser.add_subparsers(dest="command", help="What to collect")

    sub_with_defaults = argparse.ArgumentParser(add_help=False)
    sub_with_defaults.add_argument(
        "--subreddit",
        default=DEFAULT_SUBREDDIT,
        help=f"Subreddit to collect from (default: {DEFAULT_SUBREDDIT})",
    )
    sub_with_defaults.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help=f"Path to SQLite database (default: {DB_PATH})",
    )
    sub_with_defaults.add_argument(
        "--full-refresh",
        action="store_true",
        help="Re-fetch all data, ignoring stored progress",
    )
    sub_with_defaults.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers.add_parser("submissions", parents=[sub_with_defaults], help="Collect submissions")
    subparsers.add_parser("comments", parents=[sub_with_defaults], help="Collect comments")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    db_path = Path(args.db_path)
    conn = get_connection(db_path)
    create_tables(conn)

    try:
        if args.command == "submissions":
            total = fetch_submissions(conn, args.subreddit, args.full_refresh)
            print(f"Collected {total} submissions")
        elif args.command == "comments":
            total = fetch_comments(conn, args.subreddit, args.full_refresh)
            print(f"Collected {total} comments")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
