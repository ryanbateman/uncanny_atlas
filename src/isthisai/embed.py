import argparse
import json
import logging
import math
import sqlite3
import struct
import time
from pathlib import Path

import numpy as np

from isthisai.config import (
    DB_PATH,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_SIMILARITY_THRESHOLD,
    GROUNDING_THRESHOLD,
    MIN_COMMENT_LENGTH,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_TIMEOUT,
)

# Reused for the semantic-expansion eligibility gate (same non-bot list the LLM
# candidate filter uses). extract.py imports only from config, so this isn't circular.
from isthisai.extract import _BOT_AUTHORS_LOWER
from isthisai.db import create_tables, get_connection, set_metadata
from isthisai.extract import is_model_loaded

logger = logging.getLogger(__name__)

EMBEDDING_DIMS = 768


def pack_embedding(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_embedding(data: bytes, dims: int = EMBEDDING_DIMS) -> list[float]:
    return list(struct.unpack(f"<{dims}f", data))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def cosine_similarity_batch(
    query_vecs: list[list[float]], ref_vecs: list[list[float]]
) -> np.ndarray:
    queries = np.array(query_vecs, dtype=np.float32)
    refs = np.array(ref_vecs, dtype=np.float32)
    q_norms = np.linalg.norm(queries, axis=1, keepdims=True)
    r_norms = np.linalg.norm(refs, axis=1, keepdims=True)
    q_norms = np.where(q_norms == 0, 1, q_norms)
    r_norms = np.where(r_norms == 0, 1, r_norms)
    queries_normed = queries / q_norms
    refs_normed = refs / r_norms
    return queries_normed @ refs_normed.T


def call_ollama_embed(
    texts: list[str],
    model: str = OLLAMA_EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
) -> list[list[float]]:
    import urllib.request

    payload = json.dumps(
        {
            "model": model,
            "input": texts,
            "keep_alive": "5m",
        }
    ).encode("utf-8")
    url = f"{base_url.rstrip('/')}/api/embed"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["embeddings"]


def call_ollama_embed_with_retry(
    texts: list[str],
    model: str = OLLAMA_EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    max_retries: int = 3,
) -> list[list[float]]:
    for attempt in range(max_retries):
        try:
            return call_ollama_embed(texts, model=model, base_url=base_url)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"Ollama embed call failed "
                    f"(attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                raise


def get_unembedded_indicator_patterns(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT it.indicator_pattern FROM indicator_taxonomy it "
        "LEFT JOIN indicator_embeddings ie ON it.indicator_pattern = ie.indicator_pattern "
        "WHERE ie.indicator_pattern IS NULL"
    ).fetchall()
    return [r[0] for r in rows]


def get_indicator_embeddings(conn: sqlite3.Connection) -> dict[str, list[float]]:
    rows = conn.execute("SELECT indicator_pattern, embedding FROM indicator_embeddings").fetchall()
    return {r[0]: unpack_embedding(r[1]) for r in rows}


def embed_indicators(
    conn: sqlite3.Connection,
    model: str = OLLAMA_EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
) -> None:
    patterns = get_unembedded_indicator_patterns(conn)
    if not patterns:
        print("All indicator patterns already embedded.")
        return

    print(f"Embedding {len(patterns)} indicator patterns...")

    if not is_model_loaded(model=model, base_url=base_url):
        from isthisai.extract import warmup_ollama

        warmup_ollama(model=model, base_url=base_url)

    total_embedded = 0
    batch_size = EMBEDDING_BATCH_SIZE

    for i in range(0, len(patterns), batch_size):
        batch = patterns[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(patterns) + batch_size - 1) // batch_size

        try:
            embeddings = call_ollama_embed_with_retry(batch, model=model, base_url=base_url)
        except Exception as e:
            logger.error(f"Failed to embed indicator batch {batch_num}: {e}")
            continue

        for pattern, embedding in zip(batch, embeddings):
            conn.execute(
                "INSERT OR REPLACE INTO indicator_embeddings (indicator_pattern, embedding, model) "
                "VALUES (?, ?, ?)",
                (pattern, pack_embedding(embedding), model),
            )
        conn.commit()
        total_embedded += len(batch)
        print(f"  Batch {batch_num}/{total_batches}: {len(batch)} patterns embedded")

    print(f"Indicator embedding complete: {total_embedded} patterns.")


def get_unembedded_comment_ids(
    conn: sqlite3.Connection, batch_size: int = 1000, all_comments: bool = False
) -> list[str]:
    if all_comments:
        rows = conn.execute(
            "SELECT c.id FROM comments c "
            "LEFT JOIN comment_embeddings ce ON c.id = ce.comment_id "
            "WHERE ce.comment_id IS NULL "
            "LIMIT ?",
            (batch_size,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT c.id FROM comments c "
            "INNER JOIN comment_indicators ci ON c.id = ci.comment_id "
            "LEFT JOIN comment_embeddings ce ON c.id = ce.comment_id "
            "WHERE ce.comment_id IS NULL "
            "GROUP BY c.id "
            "LIMIT ?",
            (batch_size,),
        ).fetchall()
    return [r[0] for r in rows]


def embed_comments(
    conn: sqlite3.Connection,
    model: str = OLLAMA_EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    all_comments: bool = False,
) -> None:
    if all_comments:
        total_unembedded = conn.execute(
            "SELECT COUNT(*) FROM comments c "
            "LEFT JOIN comment_embeddings ce ON c.id = ce.comment_id "
            "WHERE ce.comment_id IS NULL"
        ).fetchone()[0]
    else:
        total_unembedded = conn.execute(
            "SELECT COUNT(*) FROM comments c "
            "INNER JOIN comment_indicators ci ON c.id = ci.comment_id "
            "LEFT JOIN comment_embeddings ce ON c.id = ce.comment_id "
            "WHERE ce.comment_id IS NULL"
        ).fetchone()[0]

    if total_unembedded == 0:
        print("All target comments already embedded.")
        return

    scope = "all" if all_comments else "indicator-bearing"
    print(f"Embedding {total_unembedded} {scope} comments...")

    if not is_model_loaded(model=model, base_url=base_url):
        from isthisai.extract import warmup_ollama

        warmup_ollama(model=model, base_url=base_url)

    total_embedded = 0
    batch_size = EMBEDDING_BATCH_SIZE

    while True:
        comment_ids = get_unembedded_comment_ids(
            conn, batch_size=batch_size * 10, all_comments=all_comments
        )
        if not comment_ids:
            break

        id_placeholders = ",".join(["?"] * len(comment_ids))
        comments = conn.execute(
            f"SELECT id, body FROM comments WHERE id IN ({id_placeholders})", comment_ids
        ).fetchall()

        id_to_body = {c[0]: (c[1] or "") for c in comments}
        texts = [id_to_body.get(cid, "")[:2000] for cid in comment_ids]

        for i in range(0, len(comment_ids), batch_size):
            batch_ids = comment_ids[i : i + batch_size]
            batch_texts = texts[i : i + batch_size]

            try:
                embeddings = call_ollama_embed_with_retry(
                    batch_texts, model=model, base_url=base_url
                )
            except Exception as e:
                logger.error(f"Failed to embed comment batch: {e}")
                continue

            for cid, embedding in zip(batch_ids, embeddings):
                conn.execute(
                    "INSERT OR REPLACE INTO comment_embeddings (comment_id, embedding, model) "
                    "VALUES (?, ?, ?)",
                    (cid, pack_embedding(embedding), model),
                )
            conn.commit()
            total_embedded += len(batch_ids)
            pct = min(100, int(total_embedded / total_unembedded * 100))
            print(f"  Embedded {total_embedded}/{total_unembedded} comments ({pct}%)", end="\r")

    print(f"\nComment embedding complete: {total_embedded} comments embedded.")


def semantic_expand(
    conn: sqlite3.Connection,
    threshold: float = EMBEDDING_SIMILARITY_THRESHOLD,
) -> None:
    indicator_data = get_indicator_embeddings(conn)
    if not indicator_data:
        print("No indicator embeddings found. Run isthisai-embed indicators first.")
        return

    taxonomy = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT indicator_pattern, category FROM indicator_taxonomy"
        ).fetchall()
    }

    # Skip patterns a curator has marked Noise — durable curation: a Noise phrase
    # is not a real cue, so semantic expansion must not re-introduce it.
    patterns = [p for p in indicator_data if taxonomy.get(p) != "Noise"]
    indicator_vecs = [indicator_data[p] for p in patterns]
    skipped = len(indicator_data) - len(patterns)
    if skipped:
        print(f"Skipping {skipped} Noise-marked pattern(s).")

    # Eligibility gate (mirrors the LLM candidate filter minus the keyword clause):
    # only match comments long enough to be describing something. Without this, a
    # generic seed like "AI voice" vacuums up thousands of one-word/emoji reactions —
    # they have embeddings (the whole corpus was embedded) but never cite a real tell.
    bot_ph = ",".join(["?"] * len(_BOT_AUTHORS_LOWER))
    eligible = (
        f"c.body NOT IN ('[deleted]', '[removed]') "
        f"AND LOWER(COALESCE(c.author, '')) NOT IN ({bot_ph}) "
        f"AND c.body NOT LIKE '%I am a bot%' "
        f"AND LENGTH(c.body) >= {MIN_COMMENT_LENGTH}"
    )

    total_comments = conn.execute(
        f"SELECT COUNT(*) FROM comment_embeddings ce JOIN comments c ON c.id = ce.comment_id "
        f"WHERE {eligible}",
        list(_BOT_AUTHORS_LOWER),
    ).fetchone()[0]
    if total_comments == 0:
        print("No eligible comment embeddings found. Run isthisai-embed comments first.")
        return

    print(
        f"Running semantic expansion on {total_comments} eligible comments "
        f"(>= {MIN_COMMENT_LENGTH} chars, non-bot) against {len(patterns)} indicators "
        f"(threshold={threshold})..."
    )

    batch_id = f"semantic_{int(time.time())}"
    total_matches = 0
    batch_size = 500

    # Keyset pagination by rowid (O(1) per page). OFFSET would re-scan and skip
    # every prior row each batch — pathological over the full corpus, where each
    # row carries a 3 KB embedding BLOB.
    last_rowid = 0
    processed = 0
    while True:
        rows = conn.execute(
            f"SELECT ce.rowid, ce.comment_id, ce.embedding "
            f"FROM comment_embeddings ce JOIN comments c ON c.id = ce.comment_id "
            f"WHERE ce.rowid > ? AND {eligible} "
            f"ORDER BY ce.rowid LIMIT ?",
            [last_rowid, *_BOT_AUTHORS_LOWER, batch_size],
        ).fetchall()

        if not rows:
            break

        last_rowid = rows[-1][0]
        comment_ids = [r[1] for r in rows]
        comment_vecs = [unpack_embedding(r[2]) for r in rows]

        sim_matrix = cosine_similarity_batch(comment_vecs, indicator_vecs)

        for cid, sims in zip(comment_ids, sim_matrix):
            for j, sim in enumerate(sims):
                if sim >= threshold:
                    pattern = patterns[j]
                    category = taxonomy.get(pattern)
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO comment_indicators "
                            "(comment_id, indicator, category, batch_id) "
                            "VALUES (?, ?, ?, ?)",
                            (cid, pattern, category, batch_id),
                        )
                        total_matches += 1
                    except sqlite3.IntegrityError:
                        pass

        conn.commit()
        processed += len(rows)
        pct = min(100, int(processed / total_comments * 100))
        print(
            f"  Processed {processed}/{total_comments} comments ({pct}%)",
            end="\r",
        )

    # Clear the "pending re-expansion" tracker — everything marked since the last
    # run has now been expanded against.
    set_metadata(conn, "pending_expansion", "[]")
    print(f"\nSemantic expansion complete: {total_matches:,} matches found.")


def ground_indicators(
    conn: sqlite3.Connection,
    threshold: float = GROUNDING_THRESHOLD,
    model: str = OLLAMA_EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    dry_run: bool = False,
) -> None:
    """Drop LLM-extracted cues that aren't supported by their comment.

    A text-only model invents plausible visual cues for cue-less comments. We
    catch these by embedding each cue phrase and comparing it to its comment's
    embedding: a genuine row scores high, a hallucinated one ("unnatural blinking"
    on "such a saint") scores low. Rows below the threshold are removed.

    Only LLM rows are grounded — semantic rows are similarity-grounded by
    construction, and keyword rows are grounded by literal keyword presence.
    """
    rows = conn.execute(
        "SELECT comment_id, indicator FROM comment_indicators WHERE length(batch_id) = 8"
    ).fetchall()
    if not rows:
        print("No LLM-extracted rows to ground.")
        return

    phrases = sorted({ind for _, ind in rows})
    print(
        f"Grounding {len(rows):,} LLM rows against {len(phrases):,} distinct cue "
        f"phrases (threshold={threshold})..."
    )

    if not is_model_loaded(model=model, base_url=base_url):
        from isthisai.extract import warmup_ollama

        warmup_ollama(model=model, base_url=base_url)

    # Embed every distinct cue phrase (in-memory; not persisted to keep the
    # taxonomy-only indicator_embeddings table clean).
    phrase_vec: dict[str, np.ndarray] = {}
    for i in range(0, len(phrases), EMBEDDING_BATCH_SIZE):
        batch = phrases[i : i + EMBEDDING_BATCH_SIZE]
        try:
            embs = call_ollama_embed_with_retry(batch, model=model, base_url=base_url)
        except Exception as e:
            logger.error(f"Failed to embed cue-phrase batch: {e}")
            continue
        for p, e in zip(batch, embs):
            phrase_vec[p] = np.asarray(e, dtype=np.float32)
        print(f"  embedded {min(i + EMBEDDING_BATCH_SIZE, len(phrases))}/{len(phrases)} phrases", end="\r")
    print()

    comment_vec: dict[str, np.ndarray] = {
        cid: np.frombuffer(emb, dtype="<f4")
        for cid, emb in conn.execute("SELECT comment_id, embedding FROM comment_embeddings")
    }

    def unit(v: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(v))
        return v / norm if norm else v

    ungrounded: list[tuple[str, str]] = []
    scored = 0
    for cid, ind in rows:
        cv = comment_vec.get(cid)
        pv = phrase_vec.get(ind)
        if cv is None or pv is None:
            continue  # can't ground without both embeddings — keep the row
        scored += 1
        if float(np.dot(unit(cv), unit(pv))) < threshold:
            ungrounded.append((cid, ind))

    pct = 100 * len(ungrounded) // max(scored, 1)
    print(f"Scored {scored:,} rows; {len(ungrounded):,} below threshold ({pct}%).")
    if dry_run:
        print("(dry run — nothing deleted)")
        return

    conn.executemany(
        "DELETE FROM comment_indicators WHERE comment_id = ? AND indicator = ? AND length(batch_id) = 8",
        ungrounded,
    )
    conn.commit()
    print(f"Removed {len(ungrounded):,} ungrounded LLM indicator rows.")


def categorize_indicators(
    conn: sqlite3.Connection,
    threshold: float = EMBEDDING_SIMILARITY_THRESHOLD,
    model: str = OLLAMA_EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
) -> None:
    indicator_data = get_indicator_embeddings(conn)
    if not indicator_data:
        print("No indicator embeddings found. Run isthisai-embed indicators first.")
        return

    taxonomy = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT indicator_pattern, category FROM indicator_taxonomy"
        ).fetchall()
    }

    uncategorized = conn.execute(
        "SELECT DISTINCT indicator FROM comment_indicators WHERE category IS NULL"
    ).fetchall()
    if not uncategorized:
        print("No uncategorised indicators found.")
        return

    uncategorized_phrases = [r[0] for r in uncategorized]
    print(f"Categorising {len(uncategorized_phrases)} uncategorised indicator phrases...")

    # Only match against patterns that have a real taxonomy category, so categorize
    # never invents an off-list / "Unknown" category from an orphan embedding.
    patterns = [p for p in indicator_data if p in taxonomy]
    if not patterns:
        print("No taxonomy-backed indicator embeddings to categorize against.")
        return
    pattern_vecs = [indicator_data[p] for p in patterns]
    pattern_cats = [taxonomy[p] for p in patterns]

    if not is_model_loaded(model=model, base_url=base_url):
        from isthisai.extract import warmup_ollama

        warmup_ollama(model=model, base_url=base_url)

    batch_size = 64
    all_embeds = {}

    total_batches = (len(uncategorized_phrases) + batch_size - 1) // batch_size
    for i in range(0, len(uncategorized_phrases), batch_size):
        batch = uncategorized_phrases[i : i + batch_size]
        batch_num = i // batch_size + 1
        try:
            embeds = call_ollama_embed_with_retry(batch, model=model, base_url=base_url)
        except Exception as e:
            logger.error(f"Failed to embed categorise batch {batch_num}: {e}")
            continue
        for phrase, embed in zip(batch, embeds):
            all_embeds[phrase] = embed
        print(f"  Embedded batch {batch_num}/{total_batches}", end="\r")

    print()

    if not all_embeds:
        print("No embeddings generated. Check that Ollama is running.")
        return

    print(f"Computing similarity for {len(all_embeds)} phrases against {len(patterns)} patterns...")

    query_vecs = list(all_embeds.values())
    query_phrases = list(all_embeds.keys())
    sim_matrix = cosine_similarity_batch(query_vecs, pattern_vecs)

    best_indices = np.argmax(sim_matrix, axis=1)
    best_sims = sim_matrix[np.arange(len(query_phrases)), best_indices]

    categorised_count = 0
    noise_count = 0

    for i, phrase in enumerate(query_phrases):
        best_sim = float(best_sims[i])
        best_cat = pattern_cats[int(best_indices[i])]

        if best_sim >= threshold:
            conn.execute(
                "UPDATE comment_indicators SET category = ? "
                "WHERE indicator = ? AND category IS NULL",
                (best_cat, phrase),
            )
            categorised_count += 1
        else:
            conn.execute(
                "UPDATE comment_indicators SET category = 'Noise' "
                "WHERE indicator = ? AND category IS NULL",
                (phrase,),
            )
            noise_count += 1

        if (i + 1) % 500 == 0 or i == len(query_phrases) - 1:
            print(
                f"  Assigned {i + 1}/{len(query_phrases)} phrases",
                end="\r",
            )

    conn.commit()
    print()

    still_uncategorised = conn.execute(
        "SELECT COUNT(*) FROM comment_indicators WHERE category IS NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM comment_indicators").fetchone()[0]
    print(
        f"Categorisation complete: {categorised_count:,} assigned to categories, "
        f"{noise_count:,} marked as Noise."
    )
    print(f"  Still uncategorised: {still_uncategorised:,}/{total:,}")


def show_status(conn: sqlite3.Connection) -> None:
    indicator_count = conn.execute("SELECT COUNT(*) FROM indicator_embeddings").fetchone()[0]
    indicator_total = conn.execute("SELECT COUNT(*) FROM indicator_taxonomy").fetchone()[0]
    comment_count = conn.execute("SELECT COUNT(*) FROM comment_embeddings").fetchone()[0]
    comment_with_indicators = conn.execute(
        "SELECT COUNT(DISTINCT comment_id) FROM comment_indicators"
    ).fetchone()[0]

    print("Embedding Status:")
    print(f"  Indicator patterns embedded: {indicator_count}/{indicator_total}")
    print(f"  Comments embedded:           {comment_count:,}")
    print(f"  Comments with indicators:    {comment_with_indicators:,}")

    if indicator_count > 0:
        model = conn.execute("SELECT DISTINCT model FROM indicator_embeddings LIMIT 1").fetchone()
        print(f"  Embedding model:             {model[0] if model else 'unknown'}")

    semantic_count = conn.execute(
        "SELECT COUNT(*) FROM comment_indicators WHERE batch_id LIKE 'semantic_%'"
    ).fetchone()[0]
    if semantic_count > 0:
        print(f"  Semantic expansion matches:  {semantic_count:,}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isthisai-embed",
        description="Embed-based semantic expansion for AI indicators",
    )
    subparsers = parser.add_subparsers(dest="command", help="What to do")

    indicators_parser = subparsers.add_parser(
        "indicators", help="Embed indicator taxonomy patterns"
    )
    indicators_parser.add_argument("--model", default=OLLAMA_EMBED_MODEL)
    indicators_parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    indicators_parser.add_argument("--db-path", default=str(DB_PATH))

    comments_parser = subparsers.add_parser("comments", help="Embed comments")
    comments_parser.add_argument(
        "--all",
        action="store_true",
        help="Embed every comment (not just indicator-bearing) for maximal semantic coverage",
    )
    comments_parser.add_argument("--model", default=OLLAMA_EMBED_MODEL)
    comments_parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    comments_parser.add_argument("--db-path", default=str(DB_PATH))

    semantic_parser = subparsers.add_parser(
        "semantic", help="Run semantic expansion using embeddings"
    )
    semantic_parser.add_argument("--threshold", type=float, default=EMBEDDING_SIMILARITY_THRESHOLD)
    semantic_parser.add_argument("--db-path", default=str(DB_PATH))

    categorize_parser = subparsers.add_parser(
        "categorize", help="Assign categories to uncategorised indicators using embeddings"
    )
    categorize_parser.add_argument(
        "--threshold", type=float, default=EMBEDDING_SIMILARITY_THRESHOLD
    )
    categorize_parser.add_argument("--model", default=OLLAMA_EMBED_MODEL)
    categorize_parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    categorize_parser.add_argument("--db-path", default=str(DB_PATH))

    ground_parser = subparsers.add_parser(
        "ground", help="Remove LLM cues not supported by their comment (anti-hallucination)"
    )
    ground_parser.add_argument("--threshold", type=float, default=GROUNDING_THRESHOLD)
    ground_parser.add_argument("--dry-run", action="store_true", help="Report only; delete nothing")
    ground_parser.add_argument("--model", default=OLLAMA_EMBED_MODEL)
    ground_parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    ground_parser.add_argument("--db-path", default=str(DB_PATH))

    subparsers.add_parser("status", help="Show embedding status")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    db_path = Path(args.db_path) if hasattr(args, "db_path") else DB_PATH
    if not db_path.exists():
        print(f"No database found at {db_path}")
        print("Run isthisai-collect to populate the database first.")
        return

    conn = get_connection(db_path)
    create_tables(conn)

    try:
        if args.command == "indicators":
            embed_indicators(conn, model=args.model, base_url=args.base_url)
        elif args.command == "comments":
            embed_comments(conn, model=args.model, base_url=args.base_url, all_comments=args.all)
        elif args.command == "semantic":
            semantic_expand(conn, threshold=args.threshold)
        elif args.command == "categorize":
            categorize_indicators(
                conn, threshold=args.threshold, model=args.model, base_url=args.base_url
            )
        elif args.command == "ground":
            ground_indicators(
                conn,
                threshold=args.threshold,
                model=args.model,
                base_url=args.base_url,
                dry_run=args.dry_run,
            )
        elif args.command == "status":
            show_status(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
