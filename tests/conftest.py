import sqlite3
from pathlib import Path

import pytest

from isthisai.db import create_tables, get_connection


@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    db_file = tmp_path / "test.db"
    conn = get_connection(db_file)
    create_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_submission() -> dict:
    return {
        "id": "abc123",
        "title": "Is this AI?",
        "author": "testuser",
        "created_utc": 1700000000.0,
        "score": 42,
        "num_comments": 15,
        "upvote_ratio": 0.87,
        "link_flair_text": "Image",
        "is_video": False,
        "is_self": False,
        "url": "https://example.com/image.jpg",
        "selftext": "",
        "permalink": "/r/isthisAI/comments/abc123/",
    }


@pytest.fixture
def sample_comment() -> dict:
    return {
        "id": "def456",
        "link_id": "abc123",
        "author": "commenter1",
        "body": "The fingers look weird",
        "created_utc": 1700000100.0,
        "score": 8,
        "parent_id": "abc123",
    }
