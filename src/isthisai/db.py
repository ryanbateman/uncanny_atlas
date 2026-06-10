import sqlite3
from pathlib import Path
from typing import Any

from isthisai.config import DB_PATH, DEFAULT_SUBREDDIT
from isthisai.media import classify_media_type

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    title TEXT,
    author TEXT,
    created_utc REAL NOT NULL,
    score INTEGER,
    num_comments INTEGER,
    upvote_ratio REAL,
    link_flair_text TEXT,
    is_video INTEGER,
    is_self INTEGER,
    url TEXT,
    selftext TEXT,
    permalink TEXT,
    retrieved_utc REAL,
    subreddit TEXT NOT NULL DEFAULT 'isthisAI',
    media_type TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    link_id TEXT NOT NULL,
    author TEXT,
    body TEXT,
    created_utc REAL NOT NULL,
    score INTEGER,
    parent_id TEXT,
    retrieved_utc REAL,
    subreddit TEXT NOT NULL DEFAULT 'isthisAI'
) STRICT;

CREATE TABLE IF NOT EXISTS labels (
    id TEXT NOT NULL,
    label_type TEXT NOT NULL,
    label_value TEXT NOT NULL,
    confidence REAL,
    source TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, label_type, label_value, source)
) STRICT;

CREATE TABLE IF NOT EXISTS subscriber_counts (
    date TEXT PRIMARY KEY,
    subscribers INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS _isthisai_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
) STRICT;

CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(created_utc);
CREATE INDEX IF NOT EXISTS idx_submissions_author ON submissions(author);
CREATE INDEX IF NOT EXISTS idx_comments_link_id ON comments(link_id);
CREATE INDEX IF NOT EXISTS idx_comments_created ON comments(created_utc);
CREATE INDEX IF NOT EXISTS idx_labels_id ON labels(id);
CREATE INDEX IF NOT EXISTS idx_labels_type ON labels(label_type);
"""


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT OR IGNORE INTO _isthisai_metadata (key, value) VALUES (?, ?)",
        ("schema_version", "1"),
    )
    conn.commit()
    migrate(conn)


def migrate(conn: sqlite3.Connection) -> None:
    version = get_metadata(conn, "schema_version")
    if version is None or int(version) < 2:
        migrate_to_v2(conn)
    if version is None or int(version) < 3:
        migrate_to_v3(conn)
    if version is None or int(version) < 4:
        migrate_to_v4(conn)
    if version is None or int(version) < 5:
        migrate_to_v5(conn)
    if version is None or int(version) < 6:
        migrate_to_v6(conn)
    if version is None or int(version) < 7:
        migrate_to_v7(conn)
    if version is None or int(version) < 8:
        migrate_to_v8(conn)
    if version is None or int(version) < 9:
        migrate_to_v9(conn)
    if version is None or int(version) < 10:
        migrate_to_v10(conn)


def migrate_to_v2(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(submissions)")
    columns = [row[1] for row in cur.fetchall()]
    if "subreddit" not in columns:
        conn.execute(
            "ALTER TABLE submissions ADD COLUMN subreddit TEXT NOT NULL DEFAULT 'isthisAI'"
        )
    cur = conn.execute("PRAGMA table_info(comments)")
    columns = [row[1] for row in cur.fetchall()]
    if "subreddit" not in columns:
        conn.execute("ALTER TABLE comments ADD COLUMN subreddit TEXT NOT NULL DEFAULT 'isthisAI'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_subreddit ON submissions(subreddit)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_subreddit ON comments(subreddit)")
    conn.execute("UPDATE _isthisai_metadata SET value = '2' WHERE key = 'schema_version'")
    conn.commit()


def migrate_to_v3(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS comment_indicators ("
        "comment_id TEXT NOT NULL, "
        "indicator TEXT NOT NULL, "
        "category TEXT, "
        "verdict TEXT, "
        "batch_id TEXT NOT NULL, "
        "PRIMARY KEY (comment_id, indicator)"
        ") STRICT"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS indicator_taxonomy ("
        "indicator_pattern TEXT PRIMARY KEY, "
        "category TEXT NOT NULL, "
        "subcategory TEXT"
        ") STRICT"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS extraction_runs ("
        "batch_id TEXT PRIMARY KEY, "
        "model TEXT NOT NULL, "
        "started_at TEXT, "
        "completed_at TEXT, "
        "sample_size INTEGER, "
        "comments_processed INTEGER"
        ") STRICT"
    )
    conn.execute("UPDATE _isthisai_metadata SET value = '3' WHERE key = 'schema_version'")
    conn.commit()


def migrate_to_v4(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS indicator_embeddings ("
        "indicator_pattern TEXT PRIMARY KEY, "
        "embedding BLOB NOT NULL, "
        "model TEXT NOT NULL"
        ") STRICT"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS indicator_aliases ("
        "alias TEXT PRIMARY KEY, "
        "canonical TEXT NOT NULL"
        ") STRICT"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS comment_embeddings ("
        "comment_id TEXT PRIMARY KEY, "
        "embedding BLOB NOT NULL, "
        "model TEXT NOT NULL"
        ") STRICT"
    )
    cur = conn.execute("PRAGMA table_info(comment_indicators)")
    columns = [row[1] for row in cur.fetchall()]
    if "canonical_indicator" not in columns:
        conn.execute("ALTER TABLE comment_indicators ADD COLUMN canonical_indicator TEXT")
    conn.execute("UPDATE _isthisai_metadata SET value = '4' WHERE key = 'schema_version'")
    conn.commit()


def migrate_to_v5(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(comment_indicators)")
    columns = [row[1] for row in cur.fetchall()]
    if "reviewed" not in columns:
        conn.execute("ALTER TABLE comment_indicators ADD COLUMN reviewed INTEGER DEFAULT 0")
    conn.execute("UPDATE _isthisai_metadata SET value = '5' WHERE key = 'schema_version'")
    conn.commit()


def migrate_to_v6(conn: sqlite3.Connection) -> None:
    # Drop verdict entirely. It was a comment-level guess ("leaning AI") stamped
    # onto every indicator a comment produced, never surfaced in the app, and left
    # NULL by semantic expansion — a weak, misleading signal at the indicator level.
    cur = conn.execute("PRAGMA table_info(comment_indicators)")
    columns = [row[1] for row in cur.fetchall()]
    if "verdict" in columns:
        conn.execute("ALTER TABLE comment_indicators DROP COLUMN verdict")
    conn.execute("UPDATE _isthisai_metadata SET value = '6' WHERE key = 'schema_version'")
    conn.commit()


def migrate_to_v7(conn: sqlite3.Connection) -> None:
    # Performance indexes for the web app's indicator aggregations (GROUP BY /
    # filter on these columns). Additive and idempotent; no data change. Note
    # comment_id is already covered by the (comment_id, indicator) primary key,
    # so it needs no separate index.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_category ON comment_indicators(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ci_batch ON comment_indicators(batch_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ci_canonical ON comment_indicators(canonical_indicator)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aliases_canonical ON indicator_aliases(canonical)")
    # comments(author): makes COUNT(DISTINCT author) an index-only scan (the
    # Overview's unique-commenters count). comments(subreddit, created_utc): a
    # covering index for the over-time GROUP BYs, so the scan never touches rows.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_comments_sub_created ON comments(subreddit, created_utc)"
    )
    conn.execute("UPDATE _isthisai_metadata SET value = '7' WHERE key = 'schema_version'")
    conn.commit()
    conn.execute("ANALYZE")
    conn.commit()


def migrate_to_v8(conn: sqlite3.Connection) -> None:
    # Takedown tombstones. Collection uses INSERT OR IGNORE against append-only
    # archives, so deleting a row is not enough — the next collect/import would
    # quietly re-insert it. A purge (isthisai-purge) therefore records a
    # tombstone, and insert_submissions/insert_comments skip tombstoned ids,
    # submissions, and authors. kind: 'comment' | 'submission' | 'author'.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS purge_tombstones ("
        "kind TEXT NOT NULL, "
        "id TEXT NOT NULL, "
        "purged_at TEXT DEFAULT CURRENT_TIMESTAMP, "
        "PRIMARY KEY (kind, id)"
        ") STRICT"
    )
    conn.execute("UPDATE _isthisai_metadata SET value = '8' WHERE key = 'schema_version'")
    conn.commit()


def migrate_to_v9(conn: sqlite3.Connection) -> None:
    # Raw-cue-phrase embeddings. indicator_embeddings is deliberately taxonomy-only
    # (it is the seed set semantic expansion runs from), so grounding/categorisation
    # used to embed the ~15k raw LLM phrases in-memory every run and throw them
    # away. Persisting them in their own table makes them reusable — the web app's
    # Curate -> Emerging clustering — without polluting the seed table.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS phrase_embeddings ("
        "phrase TEXT PRIMARY KEY, "
        "embedding BLOB NOT NULL, "
        "model TEXT NOT NULL"
        ") STRICT"
    )
    conn.execute("UPDATE _isthisai_metadata SET value = '9' WHERE key = 'schema_version'")
    conn.commit()


def migrate_to_v10(conn: sqlite3.Connection) -> None:
    # Formal media-type classification (video|image|text|other) for every
    # submission. Backfilled by running classify_media_type — the same function
    # insert_submissions uses — rather than a duplicated SQL CASE, so the
    # migration and the insert path can never drift apart. Re-running is safe:
    # it recomputes the same values. (Rule changes without a version bump:
    # `isthisai-enrich post-types` re-classifies in place.)
    cur = conn.execute("PRAGMA table_info(submissions)")
    if "media_type" not in [row[1] for row in cur.fetchall()]:
        conn.execute("ALTER TABLE submissions ADD COLUMN media_type TEXT")
    rows = conn.execute("SELECT id, is_video, is_self, url FROM submissions").fetchall()
    conn.executemany(
        "UPDATE submissions SET media_type = ? WHERE id = ?",
        [(classify_media_type(iv, isf, url), sid) for sid, iv, isf, url in rows],
    )
    conn.execute("UPDATE _isthisai_metadata SET value = '10' WHERE key = 'schema_version'")
    conn.commit()


def _tombstones(conn: sqlite3.Connection, kind: str) -> set[str]:
    try:
        rows = conn.execute("SELECT id FROM purge_tombstones WHERE kind = ?", (kind,)).fetchall()
    except sqlite3.OperationalError as e:
        # Only the missing-table case (pre-v8 DB) may be treated as "no
        # tombstones". Anything else — e.g. 'database is locked' — must NOT be
        # swallowed: an empty set here would silently re-import purged content.
        if "no such table" in str(e):
            return set()
        raise
    return {r[0] for r in rows}


def _strip_t3(link_id: str | None) -> str | None:
    # comments.link_id is stored both bare ("135gmrp") and prefixed ("t3_135gmrp")
    # depending on the source; tombstones store the bare submission id.
    if link_id and link_id.startswith("t3_"):
        return link_id[3:]
    return link_id


def insert_submissions(
    conn: sqlite3.Connection, items: list[dict[str, Any]], subreddit: str = DEFAULT_SUBREDDIT
) -> int:
    if not items:
        return 0
    columns = [
        "id",
        "title",
        "author",
        "created_utc",
        "score",
        "num_comments",
        "upvote_ratio",
        "link_flair_text",
        "is_video",
        "is_self",
        "url",
        "selftext",
        "permalink",
        "retrieved_utc",
        "subreddit",
        "media_type",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT OR IGNORE INTO submissions ({', '.join(columns)}) VALUES ({placeholders})"

    # Honour takedowns: never re-import purged submissions or purged authors.
    # Author comparison is case-insensitive (casing varies across sources).
    dead_subs = _tombstones(conn, "submission")
    dead_authors = {a.lower() for a in _tombstones(conn, "author")}

    rows = []
    import time

    now = time.time()
    for item in items:
        if item.get("id") in dead_subs or (item.get("author") or "").lower() in dead_authors:
            continue
        rows.append(
            (
                item.get("id"),
                item.get("title"),
                item.get("author"),
                item.get("created_utc"),
                item.get("score"),
                item.get("num_comments"),
                item.get("upvote_ratio"),
                item.get("link_flair_text"),
                int(item.get("is_video", False)) if item.get("is_video") is not None else None,
                int(item.get("is_self", False)) if item.get("is_self") is not None else None,
                item.get("url"),
                item.get("selftext"),
                item.get("permalink"),
                item.get("retrieved_utc", now),
                subreddit,
                classify_media_type(item.get("is_video"), item.get("is_self"), item.get("url")),
            )
        )

    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def insert_comments(
    conn: sqlite3.Connection, items: list[dict[str, Any]], subreddit: str = DEFAULT_SUBREDDIT
) -> int:
    if not items:
        return 0
    columns = [
        "id",
        "link_id",
        "author",
        "body",
        "created_utc",
        "score",
        "parent_id",
        "retrieved_utc",
        "subreddit",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT OR IGNORE INTO comments ({', '.join(columns)}) VALUES ({placeholders})"

    # Honour takedowns: never re-import purged comments, comments under purged
    # submissions, or comments by purged authors. Author comparison is
    # case-insensitive (casing varies across sources).
    dead_comments = _tombstones(conn, "comment")
    dead_subs = _tombstones(conn, "submission")
    dead_authors = {a.lower() for a in _tombstones(conn, "author")}

    import time

    now = time.time()
    rows = []
    for item in items:
        if (
            item.get("id") in dead_comments
            or _strip_t3(item.get("link_id")) in dead_subs
            or (item.get("author") or "").lower() in dead_authors
        ):
            continue
        rows.append(
            (
                item.get("id"),
                item.get("link_id"),
                item.get("author"),
                item.get("body"),
                item.get("created_utc"),
                item.get("score"),
                item.get("parent_id"),
                item.get("retrieved_utc", now),
                subreddit,
            )
        )

    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def get_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM _isthisai_metadata WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO _isthisai_metadata (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
