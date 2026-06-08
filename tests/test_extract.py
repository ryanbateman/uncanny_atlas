import json
import sqlite3
from pathlib import Path

import pytest

from isthisai.db import create_tables, get_connection
from isthisai.extract import (
    OPINION_KEYWORDS,
    build_extraction_prompt,
    get_comments_by_ids,
    get_opinion_comment_ids,
    insert_indicators,
    is_model_loaded,
    parse_extraction_response,
    sample_opinion_comments,
    warmup_ollama,
)


@pytest.fixture
def extract_db(tmp_path: Path) -> sqlite3.Connection:
    db_file = tmp_path / "test_extract.db"
    conn = get_connection(db_file)
    create_tables(conn)

    from isthisai.db import insert_comments

    comments = [
        {
            "id": "ec1",
            "link_id": "s1",
            "author": "user1",
            "body": "The fingers look wrong and the shadows are going different directions. Definitely AI.",
            "created_utc": 1704067200.0,
            "score": 10,
            "parent_id": "s1",
        },
        {
            "id": "ec2",
            "link_id": "s2",
            "author": "user2",
            "body": "This is clearly real, you can see the skin texture and pores.",
            "created_utc": 1704153600.0,
            "score": 5,
            "parent_id": "s2",
        },
        {
            "id": "ec3",
            "link_id": "s3",
            "author": "AutoModerator",
            "body": "This is a bot message. I am a bot and this action was performed automatically.",
            "created_utc": 1704240000.0,
            "score": 1,
            "parent_id": "s3",
        },
        {
            "id": "ec4",
            "link_id": "s4",
            "author": "user3",
            "body": "lol",
            "created_utc": 1704326400.0,
            "score": 2,
            "parent_id": "s4",
        },
        {
            "id": "ec5",
            "link_id": "s5",
            "author": "user4",
            "body": "The lighting is off and there are weird artifacts around the text. Looks generated to me.",
            "created_utc": 1704412800.0,
            "score": 15,
            "parent_id": "s5",
        },
        {
            "id": "ec6",
            "link_id": "s6",
            "author": "user5",
            "body": "[deleted]",
            "created_utc": 1704499200.0,
            "score": 0,
            "parent_id": "s6",
        },
        {
            "id": "ec7",
            "link_id": "s7",
            "author": "user6",
            "body": "The eyes have this uncanny valley feel, too smooth and glassy. AI for sure.",
            "created_utc": 1704585600.0,
            "score": 8,
            "parent_id": "s7",
        },
    ]
    insert_comments(conn, comments, subreddit="isthisAI")
    yield conn
    conn.close()


class TestOpinionFilter:
    def test_filters_bot_comments(self, extract_db):
        ids = get_opinion_comment_ids(extract_db)
        assert "ec3" not in ids

    def test_filters_deleted_comments(self, extract_db):
        ids = get_opinion_comment_ids(extract_db)
        assert "ec6" not in ids

    def test_filters_short_comments(self, extract_db):
        ids = get_opinion_comment_ids(extract_db)
        assert "ec4" not in ids

    def test_includes_opinion_comments(self, extract_db):
        ids = get_opinion_comment_ids(extract_db)
        assert "ec1" in ids
        assert "ec2" in ids

    def test_includes_keyword_comments(self, extract_db):
        ids = get_opinion_comment_ids(extract_db)
        assert "ec5" in ids
        assert "ec7" in ids


class TestSampling:
    def test_sample_returns_ids(self, extract_db):
        sample = sample_opinion_comments(extract_db, size=5)
        assert len(sample) > 0
        assert all(isinstance(sid, str) for sid in sample)

    def test_sample_respects_size(self, extract_db):
        sample = sample_opinion_comments(extract_db, size=3)
        assert len(sample) <= 3


class TestPrompt:
    def test_builds_prompt_with_comments(self):
        comments = [
            {"id": "c1", "body": "The fingers look wrong", "subreddit": "isthisAI"},
            {"id": "c2", "body": "Real for sure", "subreddit": "RealOrAI"},
        ]
        prompt = build_extraction_prompt(comments)
        assert "fingers look wrong" in prompt
        assert "Real for sure" in prompt
        assert "JSON" in prompt


class TestGetCommentsByIds:
    """The prompt is numbered in list order and the model echoes that number, so
    get_comments_by_ids MUST return rows in the requested order — SQLite's IN
    clause does not guarantee it. A mismatch shifts every cue by one comment."""

    def test_preserves_input_order(self, extract_db):
        scrambled = ["ec5", "ec1", "ec7", "ec2"]
        rows = get_comments_by_ids(extract_db, scrambled)
        assert [r["id"] for r in rows] == scrambled

    def test_skips_missing_ids(self, extract_db):
        rows = get_comments_by_ids(extract_db, ["ec2", "nope", "ec1"])
        assert [r["id"] for r in rows] == ["ec2", "ec1"]


class TestParseResponse:
    def test_valid_json(self):
        response = '```json\n[{"indicators": ["fingers", "shadows"]}]\n```'
        results = parse_extraction_response(response)
        assert len(results) == 1
        assert results[0]["indicators"] == ["fingers", "shadows"]

    def test_empty_indicators(self):
        response = '[{"indicators": []}]'
        results = parse_extraction_response(response)
        assert len(results) == 1
        assert results[0]["indicators"] == []

    def test_malformed_json(self):
        response = "This is not JSON at all"
        results = parse_extraction_response(response)
        assert results == []

    def test_multiple_comments(self):
        response = (
            '[{"indicators": ["fingers"]},'
            '{"indicators": ["skin texture"]}]'
        )
        results = parse_extraction_response(response)
        assert len(results) == 2


class TestMigrationV3:
    def test_creates_indicator_tables(self, tmp_path: Path):
        db_file = tmp_path / "test_v3.db"
        conn = get_connection(db_file)
        from isthisai.db import create_tables

        create_tables(conn)
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        assert "comment_indicators" in tables
        assert "indicator_taxonomy" in tables
        assert "extraction_runs" in tables
        conn.close()

    def test_indicator_tables_are_empty(self, tmp_path: Path):
        db_file = tmp_path / "test_v3_empty.db"
        conn = get_connection(db_file)
        from isthisai.db import create_tables

        create_tables(conn)
        count = conn.execute("SELECT COUNT(*) FROM comment_indicators").fetchone()[0]
        assert count == 0
        conn.close()


class TestInsertIndicatorsStringBug:
    def test_string_indicators_wrapped_in_list(self, extract_db):
        results = [{"indicators": "six fingers"}]
        n = insert_indicators(extract_db, results, "test_batch", ["c1"])
        assert n == 1
        row = extract_db.execute(
            "SELECT indicator FROM comment_indicators WHERE comment_id = 'c1'"
        ).fetchone()
        assert row[0] == "six fingers"

    def test_list_indicators_unchanged(self, extract_db):
        results = [{"indicators": ["fingers", "shadows"]}]
        n = insert_indicators(extract_db, results, "test_batch2", ["c2"])
        assert n == 2

    def test_empty_indicators_skipped(self, extract_db):
        results = [{"indicators": []}]
        n = insert_indicators(extract_db, results, "test_batch3", ["c3"])
        assert n == 0


class TestAttributeResults:
    """ID-keyed mapping: cues must land on the comment whose number the model
    echoed, even when entries are omitted/reordered (the misattribution bug)."""

    def test_id_keyed_mapping_handles_omitted_comment(self, extract_db):
        # Model skipped comment 2 (no cues). Without id-keying, "shadows" would
        # drift onto c2; with it, it correctly lands on c3.
        results = [
            {"id": 1, "indicators": ["fingers"]},
            {"id": 3, "indicators": ["shadows"]},
        ]
        n = insert_indicators(extract_db, results, "b_ids", ["c1", "c2", "c3"])
        assert n == 2
        rows = dict(
            extract_db.execute(
                "SELECT indicator, comment_id FROM comment_indicators WHERE batch_id='b_ids'"
            ).fetchall()
        )
        assert rows["fingers"] == "c1"
        assert rows["shadows"] == "c3"

    def test_out_of_range_and_duplicate_ids_dropped(self, extract_db):
        results = [
            {"id": 1, "indicators": ["a"]},
            {"id": 9, "indicators": ["b"]},  # out of range -> dropped
            {"id": 1, "indicators": ["c"]},  # duplicate id -> dropped
        ]
        n = insert_indicators(extract_db, results, "b_dup", ["c1", "c2"])
        assert n == 1
        row = extract_db.execute(
            "SELECT indicator FROM comment_indicators WHERE batch_id='b_dup'"
        ).fetchone()
        assert row[0] == "a"

    def test_positional_fallback_when_no_ids_and_count_matches(self, extract_db):
        results = [
            {"indicators": ["x"]},
            {"indicators": ["y"]},
        ]
        n = insert_indicators(extract_db, results, "b_pos", ["c1", "c2"])
        assert n == 2
        rows = dict(
            extract_db.execute(
                "SELECT indicator, comment_id FROM comment_indicators WHERE batch_id='b_pos'"
            ).fetchall()
        )
        assert rows["x"] == "c1"
        assert rows["y"] == "c2"

    def test_no_ids_and_count_mismatch_skips_batch(self, extract_db):
        # Ambiguous: fewer objects than comments and no ids -> attribute nothing.
        results = [{"indicators": ["z"]}]
        n = insert_indicators(extract_db, results, "b_skip", ["c1", "c2", "c3"])
        assert n == 0


class TestIsModelLoaded:
    def test_returns_true_when_model_running(self, monkeypatch):
        class FakeResp:
            def __init__(self, data):
                self._data = data

            def read(self):
                return json.dumps(self._data).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=10):
            assert req.method == "GET"
            return FakeResp({"models": [{"name": "gemma4:e4b"}]})

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert is_model_loaded(model="gemma4:e4b", base_url="http://localhost:11434") is True

    def test_returns_false_when_model_not_running(self, monkeypatch):
        class FakeResp:
            def __init__(self, data):
                self._data = data

            def read(self):
                return json.dumps(self._data).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=10):
            return FakeResp({"models": []})

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert is_model_loaded(model="gemma4:e4b", base_url="http://localhost:11434") is False

    def test_returns_false_on_error(self, monkeypatch):
        def fake_urlopen(req, timeout=10):
            raise ConnectionError("no server")

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert is_model_loaded(model="gemma4:e4b", base_url="http://localhost:11434") is False


class TestWarmupSkipsWhenLoaded:
    def test_skips_warmup_when_model_loaded(self, monkeypatch, capsys):
        called_ps = {"count": 0}
        called_chat = {"count": 0}

        class FakeResp:
            def __init__(self, data):
                self._data = data

            def read(self):
                return json.dumps(self._data).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=10, data=None):
            if req.method == "GET":
                called_ps["count"] += 1
                return FakeResp({"models": [{"name": "gemma4:e4b"}]})
            called_chat["count"] += 1
            return FakeResp({"message": {"content": "ok"}})

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        warmup_ollama(model="gemma4:e4b", base_url="http://localhost:11434")

        assert called_ps["count"] == 1
        assert called_chat["count"] == 0
        captured = capsys.readouterr()
        assert "already loaded" in captured.out
