import pytest
import responses

from isthisai.db import create_tables, get_connection
from isthisai.import_data import (
    ARCTIC_SHIFT_BASE_URL,
    _normalize_comment,
    _normalize_submission,
    import_from_arctic_shift,
)


@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "test_import.db"
    conn = get_connection(db_file)
    create_tables(conn)
    yield conn
    conn.close()


ARCTIC_SUBMISSION = {
    "id": "arctic1",
    "title": "Is this real?",
    "author": "testuser",
    "created_utc": 1747612800,
    "score": 15,
    "num_comments": 4,
    "upvote_ratio": 0.88,
    "link_flair_text": "Image",
    "is_video": False,
    "is_self": False,
    "url": "https://i.redd.it/example.png",
    "selftext": "",
    "permalink": "/r/isthisAI/comments/arctic1/",
}

ARCTIC_COMMENT = {
    "id": "arctic_c1",
    "link_id": "t3_arctic1",
    "author": "commenter",
    "body": "The hands look off",
    "created_utc": 1747613000,
    "score": 3,
    "parent_id": "t3_arctic1",
}


class TestNormalizeSubmission:
    def test_converts_integer_created_utc(self):
        result = _normalize_submission(ARCTIC_SUBMISSION)
        assert result["created_utc"] == 1747612800
        assert isinstance(result["created_utc"], int)

    def test_converts_float_created_utc(self):
        sub = dict(ARCTIC_SUBMISSION, created_utc=1747612800.5)
        result = _normalize_submission(sub)
        assert result["created_utc"] == 1747612800

    def test_converts_upvote_ratio_from_int(self):
        sub = dict(ARCTIC_SUBMISSION, upvote_ratio=88)
        result = _normalize_submission(sub)
        assert result["upvote_ratio"] == 88.0

    def test_converts_is_video_to_int(self):
        result = _normalize_submission(ARCTIC_SUBMISSION)
        assert result["is_video"] == 0
        assert result["is_self"] == 0

    def test_handles_none_fields(self):
        sub = {"id": "min1", "created_utc": 1747612800}
        result = _normalize_submission(sub)
        assert result["title"] is None
        assert result["author"] is None


class TestNormalizeComment:
    def test_strips_t3_prefix_from_link_id(self):
        result = _normalize_comment(ARCTIC_COMMENT)
        assert result["link_id"] == "arctic1"

    def test_strips_t3_prefix_from_parent_id(self):
        result = _normalize_comment(ARCTIC_COMMENT)
        assert result["parent_id"] == "arctic1"

    def test_strips_t1_prefix_from_parent_id(self):
        comment = dict(ARCTIC_COMMENT, parent_id="t1_abc123")
        result = _normalize_comment(comment)
        assert result["parent_id"] == "abc123"

    def test_handles_plain_ids(self):
        comment = {"id": "c1", "link_id": "abc", "created_utc": 1700000000, "parent_id": "abc"}
        result = _normalize_comment(comment)
        assert result["link_id"] == "abc"
        assert result["parent_id"] == "abc"


class TestImportFromArcticShift:
    @responses.activate
    def test_import_submissions(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.import_data.INITIAL_RETRY_DELAY", 0.01)
        monkeypatch.setattr("isthisai.import_data.MAX_RETRY_DELAY", 0.01)
        responses.add(
            responses.GET,
            f"{ARCTIC_SHIFT_BASE_URL}/posts/search",
            json={"data": [ARCTIC_SUBMISSION]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{ARCTIC_SHIFT_BASE_URL}/posts/search",
            json={"data": []},
            status=200,
        )
        total = import_from_arctic_shift(
            tmp_db, data_type="submissions", subreddit="isthisAI", delay=0.01
        )
        assert total == 1
        count = tmp_db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        assert count == 1

    @responses.activate
    def test_import_comments(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.import_data.INITIAL_RETRY_DELAY", 0.01)
        monkeypatch.setattr("isthisai.import_data.MAX_RETRY_DELAY", 0.01)
        responses.add(
            responses.GET,
            f"{ARCTIC_SHIFT_BASE_URL}/comments/search",
            json={"data": [ARCTIC_COMMENT]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{ARCTIC_SHIFT_BASE_URL}/comments/search",
            json={"data": []},
            status=200,
        )
        total = import_from_arctic_shift(
            tmp_db, data_type="comments", subreddit="isthisAI", delay=0.01
        )
        assert total == 1
        count = tmp_db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        assert count == 1
