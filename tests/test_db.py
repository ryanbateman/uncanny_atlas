import sqlite3

import pytest

from isthisai.db import (
    create_tables,
    get_connection,
    get_metadata,
    insert_comments,
    insert_submissions,
    migrate_to_v2,
    set_metadata,
)

EXPECTED_TABLES = {
    "submissions",
    "comments",
    "labels",
    "subscriber_counts",
    "_isthisai_metadata",
}

EXPECTED_INDEXES = {
    "idx_submissions_created",
    "idx_submissions_author",
    "idx_submissions_subreddit",
    "idx_comments_link_id",
    "idx_comments_created",
    "idx_comments_subreddit",
    "idx_labels_id",
    "idx_labels_type",
}


class TestSchema:
    def test_creates_all_tables(self, tmp_db: sqlite3.Connection) -> None:
        tables = {
            row[0]
            for row in tmp_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert EXPECTED_TABLES <= tables

    def test_creates_all_indexes(self, tmp_db: sqlite3.Connection) -> None:
        indexes = {
            row[0]
            for row in tmp_db.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert EXPECTED_INDEXES <= indexes

    def test_idempotent_creation(self, tmp_db: sqlite3.Connection) -> None:
        create_tables(tmp_db)
        tables_before = {
            row[0]
            for row in tmp_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        create_tables(tmp_db)
        tables_after = {
            row[0]
            for row in tmp_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert tables_before == tables_after

    def test_strict_mode_rejects_wrong_type(self, tmp_db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            tmp_db.execute(
                "INSERT INTO submissions (id, created_utc) VALUES (?, ?)",
                ("test_id", "not_a_number"),
            )

    def test_schema_version_metadata(self, tmp_db: sqlite3.Connection) -> None:
        version = get_metadata(tmp_db, "schema_version")
        assert version == "5"

    def test_creates_db_directory(self, tmp_path) -> None:

        db_file = tmp_path / "subdir" / "test.db"
        conn = get_connection(db_file)
        create_tables(conn)
        assert db_file.exists()
        conn.close()


class TestInsertSubmissions:
    def test_inserts_submissions(self, tmp_db: sqlite3.Connection, sample_submission) -> None:
        count = insert_submissions(tmp_db, [sample_submission])
        assert count == 1
        row = tmp_db.execute("SELECT id, title, author FROM submissions").fetchone()
        assert row == ("abc123", "Is this AI?", "testuser")

    def test_insert_or_ignore_deduplicates(
        self, tmp_db: sqlite3.Connection, sample_submission
    ) -> None:
        insert_submissions(tmp_db, [sample_submission])
        insert_submissions(tmp_db, [sample_submission])
        count = tmp_db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        assert count == 1

    def test_handles_none_fields(self, tmp_db: sqlite3.Connection) -> None:
        minimal = {"id": "min1", "created_utc": 1700000000.0}
        insert_submissions(tmp_db, [minimal])
        row = tmp_db.execute(
            "SELECT title, author, score FROM submissions WHERE id='min1'"
        ).fetchone()
        assert row == (None, None, None)

    def test_converts_booleans(self, tmp_db: sqlite3.Connection) -> None:
        sub = {
            "id": "bool1",
            "created_utc": 1700000000.0,
            "is_video": True,
            "is_self": False,
        }
        insert_submissions(tmp_db, [sub])
        row = tmp_db.execute(
            "SELECT is_video, is_self FROM submissions WHERE id='bool1'"
        ).fetchone()
        assert row == (1, 0)

    def test_empty_list_is_noop(self, tmp_db: sqlite3.Connection) -> None:
        count = insert_submissions(tmp_db, [])
        assert count == 0
        total = tmp_db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        assert total == 0


class TestInsertComments:
    def test_inserts_comments(self, tmp_db: sqlite3.Connection, sample_comment) -> None:
        count = insert_comments(tmp_db, [sample_comment])
        assert count == 1
        row = tmp_db.execute("SELECT id, link_id, author FROM comments").fetchone()
        assert row == ("def456", "abc123", "commenter1")

    def test_insert_or_ignore_deduplicates(
        self, tmp_db: sqlite3.Connection, sample_comment
    ) -> None:
        insert_comments(tmp_db, [sample_comment])
        insert_comments(tmp_db, [sample_comment])
        count = tmp_db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        assert count == 1

    def test_handles_none_fields(self, tmp_db: sqlite3.Connection) -> None:
        minimal = {"id": "c1", "link_id": "p1", "created_utc": 1700000000.0}
        insert_comments(tmp_db, [minimal])
        row = tmp_db.execute("SELECT author, body, score FROM comments WHERE id='c1'").fetchone()
        assert row == (None, None, None)


class TestMetadata:
    def test_get_missing_key_returns_none(self, tmp_db: sqlite3.Connection) -> None:
        assert get_metadata(tmp_db, "nonexistent") is None

    def test_set_and_get(self, tmp_db: sqlite3.Connection) -> None:
        set_metadata(tmp_db, "last_fetched", "1700000000")
        assert get_metadata(tmp_db, "last_fetched") == "1700000000"

    def test_upsert_metadata(self, tmp_db: sqlite3.Connection) -> None:
        set_metadata(tmp_db, "key1", "value1")
        set_metadata(tmp_db, "key1", "value2")
        assert get_metadata(tmp_db, "key1") == "value2"


class TestMigrationV2:
    def test_subreddit_columns_exist(self, tmp_db: sqlite3.Connection) -> None:
        cur = tmp_db.execute("PRAGMA table_info(submissions)")
        columns = [row[1] for row in cur.fetchall()]
        assert "subreddit" in columns
        cur = tmp_db.execute("PRAGMA table_info(comments)")
        columns = [row[1] for row in cur.fetchall()]
        assert "subreddit" in columns

    def test_subreddit_default_value(self, tmp_db: sqlite3.Connection, sample_submission) -> None:
        insert_submissions(tmp_db, [sample_submission])
        row = tmp_db.execute("SELECT subreddit FROM submissions WHERE id='abc123'").fetchone()
        assert row == ("isthisAI",)

    def test_insert_with_custom_subreddit(
        self, tmp_db: sqlite3.Connection, sample_submission
    ) -> None:
        insert_submissions(tmp_db, [sample_submission], subreddit="RealOrAI")
        row = tmp_db.execute("SELECT subreddit FROM submissions WHERE id='abc123'").fetchone()
        assert row == ("RealOrAI",)

    def test_migration_from_v1(self, tmp_path) -> None:
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("PRAGMA journal_mode=WAL")
        v1_schema = """
        CREATE TABLE submissions (
            id TEXT PRIMARY KEY, title TEXT, author TEXT,
            created_utc REAL NOT NULL, score INTEGER, num_comments INTEGER,
            upvote_ratio REAL, link_flair_text TEXT, is_video INTEGER,
            is_self INTEGER, url TEXT, selftext TEXT, permalink TEXT,
            retrieved_utc REAL
        ) STRICT;
        CREATE TABLE comments (
            id TEXT PRIMARY KEY, link_id TEXT NOT NULL, author TEXT,
            body TEXT, created_utc REAL NOT NULL, score INTEGER,
            parent_id TEXT, retrieved_utc REAL
        ) STRICT;
        CREATE TABLE _isthisai_metadata (key TEXT PRIMARY KEY, value TEXT) STRICT;
        """
        conn.executescript(v1_schema)
        conn.execute("INSERT INTO _isthisai_metadata (key, value) VALUES ('schema_version', '1')")
        conn.commit()
        migrate_to_v2(conn)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(submissions)").fetchall()]
        assert "subreddit" in columns
        version = get_metadata(conn, "schema_version")
        assert version == "2"
        conn.close()

    def test_migration_idempotent(self, tmp_db: sqlite3.Connection) -> None:
        migrate_to_v2(tmp_db)
        version = get_metadata(tmp_db, "schema_version")
        assert version == "2"
        migrate_to_v2(tmp_db)
        version = get_metadata(tmp_db, "schema_version")
        assert version == "2"
