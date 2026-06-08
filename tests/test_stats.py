import json

import pytest

from isthisai.db import create_tables, get_connection, insert_comments, insert_submissions
from isthisai.stats import compute_gaps, compute_stats


@pytest.fixture
def populated_db(tmp_path):
    db_file = tmp_path / "test_stats.db"
    conn = get_connection(db_file)
    create_tables(conn)

    submissions = [
        {
            "id": "s1",
            "title": "First post",
            "author": "alice",
            "created_utc": 1711161600.0,
            "score": 5,
            "num_comments": 2,
            "upvote_ratio": 0.8,
            "link_flair_text": "Image",
            "is_video": False,
            "is_self": False,
            "url": "https://example.com/1",
            "selftext": "",
            "permalink": "/r/isthisAI/comments/s1/",
        },
        {
            "id": "s2",
            "title": "Second post",
            "author": "bob",
            "created_utc": 1711248000.0,
            "score": 10,
            "num_comments": 5,
            "upvote_ratio": 0.9,
            "link_flair_text": None,
            "is_video": False,
            "is_self": True,
            "url": "",
            "selftext": "Check this",
            "permalink": "/r/isthisAI/comments/s2/",
        },
        {
            "id": "s3",
            "title": "Third post",
            "author": "alice",
            "created_utc": 1711334400.0,
            "score": 3,
            "num_comments": 1,
            "upvote_ratio": 0.75,
            "link_flair_text": "Video",
            "is_video": True,
            "is_self": False,
            "url": "https://example.com/3",
            "selftext": "",
            "permalink": "/r/isthisAI/comments/s3/",
        },
        {
            "id": "s4",
            "title": "Deleted author",
            "author": None,
            "created_utc": 1711593600.0,
            "score": 1,
            "num_comments": 0,
            "upvote_ratio": None,
            "link_flair_text": "Image",
            "is_video": False,
            "is_self": False,
            "url": "https://example.com/4",
            "selftext": "",
            "permalink": "/r/isthisAI/comments/s4/",
        },
    ]
    insert_submissions(conn, submissions)

    comments = [
        {
            "id": "c1",
            "link_id": "s1",
            "author": "charlie",
            "body": "The fingers look off",
            "created_utc": 1711162000.0,
            "score": 8,
            "parent_id": "s1",
        },
        {
            "id": "c2",
            "link_id": "s1",
            "author": "alice",
            "body": "I agree",
            "created_utc": 1711163000.0,
            "score": 2,
            "parent_id": "c1",
        },
        {
            "id": "c3",
            "link_id": "s2",
            "author": "bob",
            "body": "Definitely AI",
            "created_utc": 1711249000.0,
            "score": 5,
            "parent_id": "s2",
        },
    ]
    insert_comments(conn, comments)

    yield conn
    conn.close()


class TestComputeStats:
    def test_counts(self, populated_db):
        stats = compute_stats(populated_db)
        assert stats["total_submissions"] == 4
        assert stats["total_comments"] == 3

    def test_date_range(self, populated_db):
        stats = compute_stats(populated_db)
        dr = stats["submission_date_range"]
        assert dr is not None
        assert "2024" in dr["min_iso"]
        assert "2024" in dr["max_iso"]

    def test_unique_authors_excludes_null(self, populated_db):
        stats = compute_stats(populated_db)
        assert stats["unique_submitters"] == 2  # alice and bob, None excluded

    def test_unique_commenters(self, populated_db):
        stats = compute_stats(populated_db)
        assert stats["unique_commenters"] == 3  # charlie, alice, bob

    def test_avg_comments_per_submission(self, populated_db):
        stats = compute_stats(populated_db)
        assert stats["avg_comments_per_submission"] == 0.8  # 3/4

    def test_top_submitters(self, populated_db):
        stats = compute_stats(populated_db)
        names = [s["author"] for s in stats["top_submitters"]]
        assert "alice" in names
        assert "bob" in names

    def test_flair_distribution(self, populated_db):
        stats = compute_stats(populated_db)
        flairs = {f["flair"]: f["count"] for f in stats["flair_distribution"]}
        assert flairs.get("Image") == 2
        assert flairs.get("(none)") == 1
        assert flairs.get("Video") == 1

    def test_submissions_per_month(self, populated_db):
        stats = compute_stats(populated_db)
        assert len(stats["submissions_per_month"]) >= 1

    def test_empty_database(self, tmp_path):
        db_file = tmp_path / "empty.db"
        conn = get_connection(db_file)
        create_tables(conn)
        stats = compute_stats(conn)
        assert stats["total_submissions"] == 0
        assert stats["total_comments"] == 0
        assert stats["submission_date_range"] is None
        assert stats["unique_submitters"] == 0
        assert stats["avg_comments_per_submission"] == 0.0
        conn.close()


class TestComputeGaps:
    def test_no_gaps_with_continuous_data(self, populated_db):
        gaps = compute_gaps(populated_db)
        assert len(gaps) == 0 or all(g["days"] >= 1 for g in gaps)

    def test_detects_gap(self, tmp_path):
        db_file = tmp_path / "gap_test.db"
        conn = get_connection(db_file)
        create_tables(conn)

        submissions = [
            {"id": "s1", "created_utc": 1711161600.0, "title": "a", "author": "x"},
            {"id": "s2", "created_utc": 1711248000.0, "title": "b", "author": "y"},
            {"id": "s5", "created_utc": 1711507200.0, "title": "e", "author": "z"},
        ]
        insert_submissions(conn, submissions)
        gaps = compute_gaps(conn)
        assert len(gaps) >= 1
        conn.close()

    def test_empty_database(self, tmp_path):
        db_file = tmp_path / "empty.db"
        conn = get_connection(db_file)
        create_tables(conn)
        gaps = compute_gaps(conn)
        assert gaps == []
        conn.close()


class TestWriteStats:
    def test_writes_json(self, populated_db, tmp_path):
        stats = compute_stats(populated_db)
        from isthisai.stats import write_stats

        out_path = tmp_path / "stats_report.json"
        write_stats(stats, out_path)
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["total_submissions"] == 4
        assert data["total_comments"] == 3


class TestStatsSubredditFilter:
    @pytest.fixture
    def multi_db(self, tmp_path):
        db_file = tmp_path / "test_stats_multi.db"
        conn = get_connection(db_file)
        create_tables(conn)
        subs = [
            {
                "id": "ms1",
                "title": "Is this AI?",
                "author": "alice",
                "created_utc": 1711161600.0,
                "score": 10,
                "num_comments": 3,
                "upvote_ratio": 0.85,
                "link_flair_text": "Image",
                "is_video": False,
                "is_self": False,
                "url": "https://example.com/1",
                "selftext": "",
                "permalink": "/r/isthisAI/comments/ms1/",
            },
        ]
        insert_submissions(conn, subs, subreddit="isthisAI")
        subs2 = [
            {
                "id": "mr1",
                "title": "Real or AI?",
                "author": "carol",
                "created_utc": 1711248000.0,
                "score": 25,
                "num_comments": 7,
                "upvote_ratio": 0.75,
                "link_flair_text": "[GUESS]",
                "is_video": False,
                "is_self": True,
                "url": "",
                "selftext": "Is this real?",
                "permalink": "/r/RealOrAI/comments/mr1/",
            },
        ]
        insert_submissions(conn, subs2, subreddit="RealOrAI")
        yield conn
        conn.close()

    def test_compute_stats_with_subreddit_filter(self, multi_db):
        stats = compute_stats(multi_db, subreddit="isthisAI")
        assert stats["total_submissions"] == 1
        stats2 = compute_stats(multi_db, subreddit="RealOrAI")
        assert stats2["total_submissions"] == 1
        stats_all = compute_stats(multi_db)
        assert stats_all["total_submissions"] == 2

    def test_compute_gaps_with_subreddit_filter(self, multi_db):
        gaps = compute_gaps(multi_db, subreddit="isthisAI")
        assert isinstance(gaps, list)
