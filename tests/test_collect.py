import pytest
import responses

from isthisai.collect import _fetch_page, fetch_comments, fetch_submissions
from isthisai.config import PULLPUSH_BASE_URL
from isthisai.db import create_tables, get_connection, get_metadata, set_metadata


@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "test_collect.db"
    conn = get_connection(db_file)
    create_tables(conn)
    yield conn
    conn.close()


SUBMISSION_1 = {
    "id": "abc123",
    "title": "Is this AI?",
    "author": "user1",
    "created_utc": 1683021672.0,
    "score": 42,
    "num_comments": 15,
    "upvote_ratio": 0.87,
    "link_flair_text": "Image",
    "is_video": False,
    "is_self": False,
    "url": "https://example.com/img.jpg",
    "selftext": "",
    "permalink": "/r/isthisAI/comments/abc123/",
}

SUBMISSION_2 = {
    "id": "def456",
    "title": "Check this photo",
    "author": "user2",
    "created_utc": 1683108072.0,
    "score": 7,
    "num_comments": 3,
    "upvote_ratio": 0.91,
    "link_flair_text": None,
    "is_video": False,
    "is_self": True,
    "url": "",
    "selftext": "Thoughts on this?",
    "permalink": "/r/isthisAI/comments/def456/",
}

COMMENT_1 = {
    "id": "com001",
    "link_id": "abc123",
    "author": "commenter1",
    "body": "The fingers look weird",
    "created_utc": 1683022000.0,
    "score": 8,
    "parent_id": "abc123",
}


class TestFetchPage:
    @responses.activate
    def test_success(self):
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1]},
            status=200,
        )
        result = _fetch_page("/reddit/search/submission/", {"subreddit": "isthisAI", "size": 100})
        assert len(result) == 1
        assert result[0]["id"] == "abc123"

    @responses.activate
    def test_empty_data(self):
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": []},
            status=200,
        )
        result = _fetch_page("/reddit/search/submission/", {"subreddit": "isthisAI"})
        assert result == []

    @responses.activate
    def test_retry_on_429(self, monkeypatch):
        monkeypatch.setattr("isthisai.collect.INITIAL_RETRY_DELAY", 0.01)
        monkeypatch.setattr("isthisai.collect.MAX_RETRY_DELAY", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            status=429,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1]},
            status=200,
        )
        result = _fetch_page("/reddit/search/submission/", {"subreddit": "isthisAI"})
        assert len(result) == 1

    @responses.activate
    def test_retry_on_503(self, monkeypatch):
        monkeypatch.setattr("isthisai.collect.INITIAL_RETRY_DELAY", 0.01)
        monkeypatch.setattr("isthisai.collect.MAX_RETRY_DELAY", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            status=503,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1]},
            status=200,
        )
        result = _fetch_page("/reddit/search/submission/", {"subreddit": "isthisAI"})
        assert len(result) == 1

    @responses.activate
    def test_returns_none_after_max_retries(self, monkeypatch):
        monkeypatch.setattr("isthisai.collect.INITIAL_RETRY_DELAY", 0.01)
        monkeypatch.setattr("isthisai.collect.MAX_RETRY_DELAY", 0.01)
        for _ in range(5):
            responses.add(
                responses.GET,
                f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
                status=503,
            )
        result = _fetch_page("/reddit/search/submission/", {"subreddit": "isthisAI"})
        assert result is None

    @responses.activate
    def test_returns_none_on_400(self):
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"message": "Bad request"},
            status=400,
        )
        result = _fetch_page("/reddit/search/submission/", {"subreddit": "isthisAI"})
        assert result is None


class TestFetchSubmissions:
    @responses.activate
    def test_fetches_single_page_then_empty(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1, SUBMISSION_2]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": []},
            status=200,
        )
        total = fetch_submissions(tmp_db, subreddit="isthisAI")
        assert total == 2
        count = tmp_db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        assert count == 2

    @responses.activate
    def test_stops_on_empty_page(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": []},
            status=200,
        )
        total = fetch_submissions(tmp_db, subreddit="isthisAI")
        assert total == 1

    @responses.activate
    def test_paginates_with_after(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_PAGE_SIZE", 2)
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1, SUBMISSION_2]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": []},
            status=200,
        )
        total = fetch_submissions(tmp_db, subreddit="isthisAI")
        assert total == 3

    def test_resumes_from_metadata(self, tmp_db):
        set_metadata(tmp_db, "last_submission_utc_isthisAI", "1683021672")
        after_ts = float(get_metadata(tmp_db, "last_submission_utc_isthisAI"))
        assert after_ts == 1683021672.0

    @responses.activate
    def test_full_refresh_ignores_stored_progress(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        set_metadata(tmp_db, "last_submission_utc_isthisAI", "1700000000")
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": []},
            status=200,
        )
        total = fetch_submissions(tmp_db, subreddit="isthisAI", full_refresh=True)
        assert total >= 1


class TestFetchComments:
    @responses.activate
    def test_fetches_comments(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/comment/",
            json={"data": [COMMENT_1]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/comment/",
            json={"data": []},
            status=200,
        )
        total = fetch_comments(tmp_db, subreddit="isthisAI")
        assert total == 1
        count = tmp_db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        assert count == 1

    @responses.activate
    def test_stops_on_empty_page(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/comment/",
            json={"data": [COMMENT_1]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/comment/",
            json={"data": []},
            status=200,
        )
        total = fetch_comments(tmp_db, subreddit="isthisAI")
        assert total == 1


class TestSubredditStored:
    @responses.activate
    def test_subreddit_stored_in_submissions(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": [SUBMISSION_1]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/submission/",
            json={"data": []},
            status=200,
        )
        fetch_submissions(tmp_db, subreddit="RealOrAI")
        row = tmp_db.execute("SELECT subreddit FROM submissions WHERE id='abc123'").fetchone()
        assert row == ("RealOrAI",)

    @responses.activate
    def test_subreddit_stored_in_comments(self, tmp_db, monkeypatch):
        monkeypatch.setattr("isthisai.collect.PULLPUSH_DELAY_SECONDS", 0.01)
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/comment/",
            json={"data": [COMMENT_1]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PULLPUSH_BASE_URL}/reddit/search/comment/",
            json={"data": []},
            status=200,
        )
        fetch_comments(tmp_db, subreddit="RealOrAI")
        row = tmp_db.execute("SELECT subreddit FROM comments WHERE id='com001'").fetchone()
        assert row == ("RealOrAI",)
