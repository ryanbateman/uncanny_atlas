import json
import sqlite3
import struct
from pathlib import Path

import pytest

from isthisai.db import create_tables, get_connection
from isthisai.embed import (
    EMBEDDING_DIMS,
    cosine_similarity,
    cosine_similarity_batch,
    get_unembedded_indicator_patterns,
    pack_embedding,
    semantic_expand,
    unpack_embedding,
)


def make_embedding(values=None):
    if values is None:
        values = [0.1] * EMBEDDING_DIMS
    return values


@pytest.fixture
def embed_db(tmp_path: Path) -> sqlite3.Connection:
    db_file = tmp_path / "test_embed.db"
    conn = get_connection(db_file)
    create_tables(conn)

    from isthisai.db import insert_comments

    comments = [
        {
            "id": "ec1",
            "link_id": "s1",
            "author": "user1",
            "body": "The fingers look wrong and the shadows are off.",
            "created_utc": 1704067200.0,
            "score": 10,
            "parent_id": "s1",
        },
        {
            "id": "ec2",
            "link_id": "s2",
            "author": "user2",
            "body": "The skin texture and pores look real to me.",
            "created_utc": 1704153600.0,
            "score": 5,
            "parent_id": "s2",
        },
        {
            "id": "ec3",
            "link_id": "s3",
            "author": "user3",
            "body": "The lighting is off and there are weird artifacts around the text.",
            "created_utc": 1704412800.0,
            "score": 15,
            "parent_id": "s3",
        },
    ]
    insert_comments(conn, comments, subreddit="isthisAI")

    conn.execute(
        "INSERT INTO comment_indicators (comment_id, indicator, category, batch_id) "
        "VALUES ('ec1', 'wrong fingers', 'Anatomy', 'test_batch')"
    )
    conn.execute(
        "INSERT INTO comment_indicators (comment_id, indicator, category, batch_id) "
        "VALUES ('ec1', 'shadows off', 'Physics', 'test_batch')"
    )
    conn.execute(
        "INSERT INTO comment_indicators (comment_id, indicator, category, batch_id) "
        "VALUES ('ec2', 'skin texture', 'Style', 'test_batch')"
    )
    conn.commit()
    yield conn
    conn.close()


class TestEmbeddingSerialization:
    def test_pack_unpack_roundtrip(self):
        vec = [0.1, 0.2, 0.3, -0.4, 0.5] + [0.0] * (EMBEDDING_DIMS - 5)
        packed = pack_embedding(vec)
        unpacked = unpack_embedding(packed)
        assert len(unpacked) == EMBEDDING_DIMS
        for a, b in zip(vec, unpacked):
            assert abs(a - b) < 1e-6

    def test_pack_produces_bytes(self):
        vec = [0.1] * EMBEDDING_DIMS
        packed = pack_embedding(vec)
        assert isinstance(packed, bytes)
        assert len(packed) == EMBEDDING_DIMS * 4

    def test_unpack_produces_list(self):
        vec = [0.1] * EMBEDDING_DIMS
        packed = pack_embedding(vec)
        unpacked = unpack_embedding(packed)
        assert isinstance(unpacked, list)
        assert len(unpacked) == EMBEDDING_DIMS


class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 3)
        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 2)
        b = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMS - 2)
        sim = cosine_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 2)
        b = [-1.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 2)
        sim = cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_zero_vector(self):
        vec = [1.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 2)
        zeros = [0.0] * EMBEDDING_DIMS
        assert cosine_similarity(vec, zeros) == 0.0

    def test_batch_similarity(self):
        a = [1.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 2)
        b = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMS - 2)
        result = cosine_similarity_batch([a, b], [a, b])
        assert abs(result[0][0] - 1.0) < 1e-6
        assert abs(result[0][1]) < 1e-6
        assert abs(result[1][0]) < 1e-6
        assert abs(result[1][1] - 1.0) < 1e-6


class TestSchemaV4Migration:
    def test_creates_embedding_tables(self, tmp_path: Path):
        db_file = tmp_path / "test_v4.db"
        conn = get_connection(db_file)
        create_tables(conn)
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        assert "indicator_embeddings" in tables
        assert "indicator_aliases" in tables
        assert "comment_embeddings" in tables
        conn.close()

    def test_adds_canonical_indicator_column(self, tmp_path: Path):
        db_file = tmp_path / "test_v4_col.db"
        conn = get_connection(db_file)
        create_tables(conn)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(comment_indicators)").fetchall()]
        assert "canonical_indicator" in columns
        conn.close()


class TestUnembeddedIndicators:
    def test_finds_unembedded_patterns(self, embed_db):
        conn = embed_db
        conn.execute(
            "INSERT INTO indicator_taxonomy (indicator_pattern, category) VALUES ('wrong fingers', 'Anatomy')"
        )
        conn.execute(
            "INSERT INTO indicator_taxonomy (indicator_pattern, category) VALUES ('shadows off', 'Physics')"
        )
        conn.commit()

        patterns = get_unembedded_indicator_patterns(conn)
        assert len(patterns) == 2
        assert "wrong fingers" in patterns

    def test_skips_embedded_patterns(self, embed_db):
        conn = embed_db
        conn.execute(
            "INSERT INTO indicator_taxonomy (indicator_pattern, category) VALUES ('wrong fingers', 'Anatomy')"
        )
        conn.execute(
            "INSERT INTO indicator_embeddings (indicator_pattern, embedding, model) "
            "VALUES ('wrong fingers', ?, 'test-model')",
            (pack_embedding(make_embedding()),),
        )
        conn.commit()

        patterns = get_unembedded_indicator_patterns(conn)
        assert "wrong fingers" not in patterns


class TestSemanticExpand:
    def test_finds_matches_above_threshold(self, embed_db):
        conn = embed_db

        anim_vec = [1.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 2)
        physics_vec = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMS - 2)

        conn.execute(
            "INSERT INTO indicator_taxonomy (indicator_pattern, category) VALUES ('weird eyes', 'Anatomy')"
        )
        conn.execute(
            "INSERT INTO indicator_taxonomy (indicator_pattern, category) VALUES ('bad lighting', 'Physics')"
        )
        conn.execute(
            "INSERT INTO indicator_embeddings (indicator_pattern, embedding, model) "
            "VALUES ('weird eyes', ?, 'test-model')",
            (pack_embedding(anim_vec),),
        )
        conn.execute(
            "INSERT INTO indicator_embeddings (indicator_pattern, embedding, model) "
            "VALUES ('bad lighting', ?, 'test-model')",
            (pack_embedding(physics_vec),),
        )

        anim_comment_vec = [0.9, 0.1] + [0.0] * (EMBEDDING_DIMS - 2)
        physics_comment_vec = [0.1, 0.9] + [0.0] * (EMBEDDING_DIMS - 2)

        conn.execute(
            "INSERT INTO comment_embeddings (comment_id, embedding, model) VALUES (?, ?, 'test-model')",
            ("ec1", pack_embedding(anim_comment_vec)),
        )
        conn.execute(
            "INSERT INTO comment_embeddings (comment_id, embedding, model) VALUES (?, ?, 'test-model')",
            ("ec2", pack_embedding(physics_comment_vec)),
        )
        conn.commit()

        semantic_expand(conn, threshold=0.5)

        rows = conn.execute(
            "SELECT comment_id, indicator FROM comment_indicators WHERE batch_id LIKE 'semantic_%'"
        ).fetchall()

        semantic_indicators = {r[1] for r in rows}
        assert "weird eyes" in semantic_indicators
        assert "bad lighting" in semantic_indicators

    def test_skips_matches_below_threshold(self, embed_db):
        conn = embed_db
        orthogonal_vec_a = [1.0, 0.0] + [0.0] * (EMBEDDING_DIMS - 2)
        orthogonal_vec_b = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMS - 2)

        conn.execute(
            "INSERT INTO indicator_taxonomy (indicator_pattern, category) VALUES ('irrelevant', 'Meta')"
        )
        conn.execute(
            "INSERT INTO indicator_embeddings (indicator_pattern, embedding, model) "
            "VALUES ('irrelevant', ?, 'test-model')",
            (pack_embedding(orthogonal_vec_a),),
        )
        conn.execute(
            "INSERT INTO comment_embeddings (comment_id, embedding, model) VALUES (?, ?, 'test-model')",
            ("ec3", pack_embedding(orthogonal_vec_b)),
        )
        conn.commit()

        semantic_expand(conn, threshold=0.99)

        rows = conn.execute(
            "SELECT COUNT(*) FROM comment_indicators WHERE batch_id LIKE 'semantic_%'"
        ).fetchone()
        assert rows[0] == 0


class TestCallOllamaEmbed:
    def test_embed_returns_vectors(self, monkeypatch):
        import isthisai.embed as mod

        fake_embedding = [0.1] * EMBEDDING_DIMS

        class FakeResp:
            def __init__(self):
                self._data = json.dumps({"embeddings": [fake_embedding]}).encode()

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=10, data=None):
            return FakeResp()

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        results = mod.call_ollama_embed(["test text"], model="nomic-embed-text")
        assert len(results) == 1
        assert len(results[0]) == EMBEDDING_DIMS


class TestEmbedStatus:
    def test_status_output(self, embed_db, capsys):
        from isthisai.embed import show_status

        show_status(embed_db)
        captured = capsys.readouterr()
        assert "Embedding Status" in captured.out
        assert "Indicator patterns embedded" in captured.out


class TestEmergenceChannel:
    """phrase_embeddings persistence + the categorize valve (no auto-Noise)."""

    @staticmethod
    def _vec(first: float, second: float = 0.0):
        v = [0.0] * EMBEDDING_DIMS
        v[0], v[1] = first, second
        return v

    def _patch_ollama(self, monkeypatch, vec_for):
        # Patch in embed's namespace: is_model_loaded is imported INTO isthisai.embed.
        import isthisai.embed as mod

        monkeypatch.setattr(mod, "is_model_loaded", lambda **kw: True)
        monkeypatch.setattr(
            mod,
            "call_ollama_embed_with_retry",
            lambda texts, model=None, base_url=None, **kw: [vec_for(t) for t in texts],
        )

    def _seed_taxonomy(self, conn):
        conn.execute(
            "INSERT INTO indicator_taxonomy (indicator_pattern, category, subcategory) "
            "VALUES ('weird hands', 'Anatomy', NULL)"
        )
        conn.execute(
            "INSERT INTO indicator_embeddings (indicator_pattern, embedding, model) "
            "VALUES ('weird hands', ?, 'test-model')",
            (pack_embedding(self._vec(1.0)),),
        )
        conn.commit()

    def test_categorize_persists_phrase_embeddings_and_assigns(self, embed_db, monkeypatch):
        from isthisai.embed import categorize_indicators

        self._seed_taxonomy(embed_db)
        embed_db.execute(
            "INSERT INTO comment_indicators (comment_id, indicator, category, batch_id) "
            "VALUES ('ec3', 'mangled fingers', NULL, 'abcd1234')"
        )
        embed_db.commit()
        # Near the seed vector -> above threshold -> assigned the seed's category.
        self._patch_ollama(monkeypatch, lambda t: self._vec(0.9, 0.1))

        categorize_indicators(embed_db, threshold=0.5)

        row = embed_db.execute(
            "SELECT embedding, model FROM phrase_embeddings WHERE phrase = 'mangled fingers'"
        ).fetchone()
        assert row is not None
        assert unpack_embedding(row[0])[0] == pytest.approx(0.9)
        cat = embed_db.execute(
            "SELECT category FROM comment_indicators WHERE indicator = 'mangled fingers'"
        ).fetchone()[0]
        assert cat == "Anatomy"

    def test_categorize_below_threshold_stays_uncategorised(self, embed_db, monkeypatch, capsys):
        """The valve: far-from-every-seed phrases must NOT be auto-Noised."""
        from isthisai.embed import categorize_indicators

        self._seed_taxonomy(embed_db)
        embed_db.execute(
            "INSERT INTO comment_indicators (comment_id, indicator, category, batch_id) "
            "VALUES ('ec3', 'totally novel tell', NULL, 'abcd1234')"
        )
        embed_db.commit()
        # Orthogonal to the seed -> below any reasonable threshold.
        self._patch_ollama(monkeypatch, lambda t: self._vec(0.0, 1.0))

        categorize_indicators(embed_db, threshold=0.99)

        cat = embed_db.execute(
            "SELECT category FROM comment_indicators WHERE indicator = 'totally novel tell'"
        ).fetchone()[0]
        assert cat is None  # stays uncategorised — specifically NOT 'Noise'
        assert (
            embed_db.execute(
                "SELECT COUNT(*) FROM phrase_embeddings WHERE phrase = 'totally novel tell'"
            ).fetchone()[0]
            == 1
        )  # embedding persisted even though no category was assigned
        assert "left uncategorised" in capsys.readouterr().out

    def test_ground_persists_phrase_embeddings(self, embed_db, monkeypatch):
        from isthisai.embed import ground_indicators

        # An LLM row (8-char batch id) whose comment has an embedding; identical
        # vectors -> similarity 1.0 -> survives any threshold.
        embed_db.execute(
            "INSERT INTO comment_indicators (comment_id, indicator, category, batch_id) "
            "VALUES ('ec1', 'grounded cue', NULL, 'abcd1234')"
        )
        embed_db.execute(
            "INSERT INTO comment_embeddings (comment_id, embedding, model) "
            "VALUES ('ec1', ?, 'test-model')",
            (pack_embedding(self._vec(1.0)),),
        )
        embed_db.commit()
        self._patch_ollama(monkeypatch, lambda t: self._vec(1.0))

        ground_indicators(embed_db, threshold=0.5)

        assert (
            embed_db.execute(
                "SELECT COUNT(*) FROM phrase_embeddings WHERE phrase = 'grounded cue'"
            ).fetchone()[0]
            == 1
        )
        assert (
            embed_db.execute(
                "SELECT COUNT(*) FROM comment_indicators WHERE indicator = 'grounded cue'"
            ).fetchone()[0]
            == 1
        )  # high similarity -> row kept
