import argparse
import json
import logging
import re
import signal
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from isthisai.config import (
    DB_PATH,
    EXTRACTION_BATCH_SIZE,
    EXTRACTION_SAMPLE_SIZE,
    MIN_COMMENT_LENGTH,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_TIMEOUT,
)
from isthisai.db import create_tables, get_connection, set_metadata

logger = logging.getLogger(__name__)

# Topical / authenticity-judgment words only — deliberately NOT visual-cue words.
# An earlier version included cue terms (finger, hand, eye, shadow, reflection,
# lighting, texture, …); filtering the LLM sample for those pre-named the cues and
# made the discovered taxonomy circular. These generic words just identify a comment
# as engaging the "is this AI?" question; semantic expansion (corpus-wide, ungated)
# is what generalizes to cues, including the ~31% of cue-citing comments that match
# no keyword. If you change this list, update the mirror in web/src/lib/server/queries.ts.
OPINION_KEYWORDS = [
    "AI",
    "real",
    "fake",
    "generated",
    "obvious",
    "look",
]

OPINION_BOT_AUTHORS = (
    "AutoModerator",
    "qualityvote2",
    "RealOrAI-Bot",
    "isthisAI-ModTeam",
    "RealOrAI-ModTeam",
    "isthisai-bot",
    "BotDefense",
)
# Lowercased for case-insensitive matching — author casing varies in the data
# (e.g. the filter previously had "RealOrAI-bot" but the account is "RealOrAI-Bot",
# so its ~12k templated comments leaked into extraction).
_BOT_AUTHORS_LOWER = tuple(a.lower() for a in OPINION_BOT_AUTHORS)

# Two kinds of phrase that are never a visual cue, dropped at extraction:
#   1. Post-location / source platforms — where an image was seen, not a property of it.
#   2. Verdicts / conclusions — "definitely AI", "not AI", "100% real" — judgements, not
#      evidence; left unfiltered they swamp the rankings by sheer frequency.
# Deliberately NOT included (these are allowed through as real cues): generation tools
# (Photoshop, Midjourney), bare subjects (dog, art, background), and watermarks /
# provenance (SynthID) — a SynthID watermark is strong evidence of AI, the opposite of
# noise. Exact, case-insensitive match ("AI Generated" == "ai generated"); it can't
# catch every verdict compound — that's a prompt/curation problem, not a list one.
# (The Run book's "two upstream filters" note shows this list — keep it in sync.)
STOP_INDICATORS = {
    # post-location / source platforms
    "facebook", "instagram", "tiktok", "twitter", "reddit", "google",
    # verdicts / conclusions (a judgement, not visual evidence)
    "ai", "not ai", "fake", "real", "obvious", "obviously ai", "obviously fake",
    "obvious ai", "looks ai", "looks fake", "looks real", "doesn't look real",
    "does not look real", "ai generated", "ai-generated", "ai look", "100% ai",
    "100% real", "definitely ai", "clearly ai", "ai art", "ai image", "ai images",
    "ai slop", "not real", "so fake", "generated", "real or ai", "is this ai",
}


def is_stop_indicator(phrase: str) -> bool:
    """True if the phrase is a verdict/tool/subject rather than a real visual cue."""
    return phrase.strip().lower() in STOP_INDICATORS


# The fixed taxonomy category set. The LLM sometimes invents off-list labels
# (e.g. "AI images", "Artifact", "Unknown"); normalize_category coerces near
# matches and rejects the rest so strays never enter the taxonomy.
TAXONOMY_CATEGORIES = (
    "Anatomy", "Physics", "Artifacts", "Style",
    "Text & Detail", "Motion", "Context", "Meta",
)
_CATEGORY_BY_LOWER = {c.lower(): c for c in TAXONOMY_CATEGORIES}
_CATEGORY_ALIASES = {
    "artifact": "Artifacts",
    "ai images": "Artifacts",
    "ai image": "Artifacts",
    "text and detail": "Text & Detail",
    "text&detail": "Text & Detail",
    "detail": "Text & Detail",
    "anatomical": "Anatomy",
    "lighting": "Physics",
}


def normalize_category(category: str | None) -> str | None:
    """Map an LLM-returned category to a valid taxonomy category, or None if off-list."""
    key = (category or "").strip().lower()
    return _CATEGORY_BY_LOWER.get(key) or _CATEGORY_ALIASES.get(key)


def persist_stop_indicators(conn: sqlite3.Connection) -> None:
    """Persist the stop-list to metadata so the web app can show what's auto-excluded."""
    set_metadata(conn, "stop_indicators", json.dumps(sorted(STOP_INDICATORS)))


def get_opinion_comment_ids(conn: sqlite3.Connection, subreddit: str | None = None) -> list[str]:
    sub_where, sub_params = _sub_where(subreddit)
    keyword_clauses = " OR ".join(["body LIKE ?" for _ in OPINION_KEYWORDS])
    keyword_params = [f"%{kw}%" for kw in OPINION_KEYWORDS]
    bot_placeholders = ",".join(["?"] * len(OPINION_BOT_AUTHORS))
    sql = (
        f"SELECT id FROM comments "
        f"WHERE body IS NOT NULL "
        f"AND body NOT IN ('[deleted]', '[removed]') "
        f"AND LOWER(author) NOT IN ({bot_placeholders}) "
        f"AND body NOT LIKE '%I am a bot%' "
        f"AND LENGTH(body) >= {MIN_COMMENT_LENGTH} "
        f"AND ({keyword_clauses}) "
        f"{sub_where} "
        f"ORDER BY id"
    )
    params = list(_BOT_AUTHORS_LOWER) + keyword_params + sub_params
    rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def _sub_where(subreddit: str | None) -> tuple[str, list[str]]:
    if subreddit:
        return "AND subreddit = ?", [subreddit]
    return "", []


def sample_opinion_comments(
    conn: sqlite3.Connection,
    size: int = EXTRACTION_SAMPLE_SIZE,
    subreddit: str | None = None,
) -> list[str]:
    sub_and = "AND subreddit = ?" if subreddit else ""
    sub_params = [subreddit] if subreddit else []
    keyword_clauses = " OR ".join(["body LIKE ?" for _ in OPINION_KEYWORDS])
    keyword_params = [f"%{kw}%" for kw in OPINION_KEYWORDS]
    bot_placeholders = ",".join(["?"] * len(OPINION_BOT_AUTHORS))

    subreddits = (
        [subreddit]
        if subreddit
        else [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT subreddit FROM comments WHERE subreddit IS NOT NULL"
            ).fetchall()
        ]
    )
    if not subreddits:
        return []

    total_count = conn.execute(
        f"SELECT COUNT(*) FROM comments "
        f"WHERE body IS NOT NULL "
        f"AND body NOT IN ('[deleted]', '[removed]') "
        f"AND LOWER(author) NOT IN ({bot_placeholders}) "
        f"AND body NOT LIKE '%I am a bot%' "
        f"AND LENGTH(body) >= {MIN_COMMENT_LENGTH} "
        f"AND ({keyword_clauses}) "
        f"{sub_and}",
        list(_BOT_AUTHORS_LOWER) + keyword_params + sub_params,
    ).fetchone()[0]

    if total_count == 0:
        return []

    limit = min(size, total_count)
    rows = conn.execute(
        f"SELECT id FROM comments "
        f"WHERE body IS NOT NULL "
        f"AND body NOT IN ('[deleted]', '[removed]') "
        f"AND LOWER(author) NOT IN ({bot_placeholders}) "
        f"AND body NOT LIKE '%I am a bot%' "
        f"AND LENGTH(body) >= {MIN_COMMENT_LENGTH} "
        f"AND ({keyword_clauses}) "
        f"{sub_and} "
        f"ORDER BY RANDOM() LIMIT ?",
        list(_BOT_AUTHORS_LOWER) + keyword_params + sub_params + [limit],
    ).fetchall()
    return [r[0] for r in rows]


def get_comments_by_ids(conn: sqlite3.Connection, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"SELECT id, body, subreddit FROM comments WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    by_id = {r[0]: {"id": r[0], "body": r[1], "subreddit": r[2]} for r in rows}
    # SQLite's `IN` returns rows in storage order, NOT the order of `ids`. The
    # extraction prompt numbers comments in list order and the model echoes that
    # number back, so the returned order MUST match the input order or every cue
    # gets attributed to the wrong comment. Preserve order; skip ids with no row.
    return [by_id[i] for i in ids if i in by_id]


def build_extraction_prompt(comments: list[dict[str, Any]]) -> str:
    lines = []
    for i, c in enumerate(comments, 1):
        body = (c["body"] or "").replace('"', "'")[:500]
        lines.append(f'{i}. "{body}"')
    comments_text = "\n".join(lines)
    return (
        "You are studying comments from subreddits where people judge whether an "
        "image or video is AI-generated. For each numbered comment, extract the "
        "specific visual or audio CUES the commenter points to as evidence.\n\n"
        "A cue is a concrete, observable feature of the media itself — for example: "
        "six fingers, warped background text, plastic-looking skin, mismatched "
        "earrings, unnatural blinking, inconsistent shadows, garbled hands.\n\n"
        "Do NOT extract:\n"
        "- the plain subject of the image (dog, woman, car, tattoo) unless a flaw in "
        "it is named;\n"
        "- bare verdicts or opinions (it's AI, fake, looks real, obvious, the vibes "
        "are off);\n"
        "- tools or platforms (Photoshop, Midjourney, ChatGPT, Sora, Gemini);\n"
        "- meta-commentary or reasoning with no concrete cue.\n\n"
        "Keep each cue a short phrase (1-6 words), lowercase, describing the flaw "
        "itself rather than quoting the whole sentence.\n\n"
        "For each comment return an object with:\n"
        '1. "id": the comment\'s number, EXACTLY as shown. This ties the cues to the '
        "correct comment, so it must be accurate.\n"
        '2. "indicators": a list of short cue phrases.\n\n'
        "Skip any comment that names no concrete cue — do not emit an object for it.\n\n"
        "Example input:\n"
        '1. "the hands are mangled and there are six fingers on the left one"\n'
        '2. "100% fake lmao"\n'
        '3. "shadows fall the wrong way and the window reflection is missing"\n'
        "Example output:\n"
        '[{"id": 1, "indicators": ["mangled hands", "six fingers"]},\n'
        ' {"id": 3, "indicators": ["inconsistent shadows", "missing reflection"]}]\n'
        "(Comment 2 is skipped: it names no concrete cue.)\n\n"
        "Return ONLY the JSON array for the comments below.\n\n"
        f"Comments:\n{comments_text}\n\nJSON:"
    )


def is_model_loaded(model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL) -> bool:
    import urllib.request

    url = f"{base_url.rstrip('/')}/api/ps"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        running_models = [m.get("name", "") for m in data.get("models", [])]
        return model in running_models
    except Exception:
        return False


def warmup_ollama(model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL) -> None:
    import urllib.request

    if is_model_loaded(model=model, base_url=base_url):
        print(f"Model {model} already loaded in memory, skipping warmup.")
        return

    print(f"Warming up model {model}...")
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
            "think": False,
            "options": {"num_predict": 1, "num_ctx": OLLAMA_NUM_CTX},
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
    ).encode("utf-8")
    url = f"{base_url.rstrip('/')}/api/chat"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            json.loads(resp.read().decode("utf-8"))
        print(f"Model {model} loaded and will stay in memory for {OLLAMA_KEEP_ALIVE}.")
    except Exception as e:
        print(f"Warning: warmup failed ({e}). Proceeding anyway — first batch may be slow.")


def call_ollama(
    prompt: str, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL, num_predict: int = 500
) -> str:
    import urllib.request

    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {"num_predict": num_predict, "num_ctx": OLLAMA_NUM_CTX},
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
    ).encode("utf-8")
    url = f"{base_url.rstrip('/')}/api/chat"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["message"]["content"]


def call_ollama_with_retry(
    prompt: str,
    model: str = OLLAMA_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    max_retries: int = 3,
    num_predict: int = 500,
) -> str:
    for attempt in range(max_retries):
        try:
            return call_ollama(prompt, model=model, base_url=base_url, num_predict=num_predict)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"Ollama call failed "
                    f"(attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                raise


def parse_extraction_response(response_text: str) -> list[dict[str, Any]]:
    text = response_text.strip()
    json_start = text.find("[")
    json_end = text.rfind("]") + 1
    if json_start == -1 or json_end == 0:
        logger.warning("No JSON array found in response")
        return []
    try:
        return json.loads(text[json_start:json_end])
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON response")
        return []


def attribute_results(
    results: list[dict[str, Any]], comment_ids: list[str]
) -> list[tuple[str, dict[str, Any]]]:
    """Pair each result object with the comment it belongs to.

    Primary path: map by the model-echoed 1-based ``id`` field, so cues are tied
    to the right comment even if the model omits, reorders, or merges entries.
    Out-of-range and duplicate ids are dropped rather than guessed.

    Fallback: only when *no* object carries an id and the object count exactly
    matches the batch do we fall back to legacy positional mapping. Anything else
    is too ambiguous to attribute safely, so it's skipped (with a warning).
    """
    n = len(comment_ids)
    objs = [r for r in results if isinstance(r, dict)]
    has_ids = any(r.get("id") is not None for r in objs)

    if has_ids:
        pairs: list[tuple[str, dict[str, Any]]] = []
        seen: set[int] = set()
        for r in objs:
            try:
                idx = int(r.get("id"))
            except (TypeError, ValueError):
                continue
            if idx < 1 or idx > n or idx in seen:
                continue
            seen.add(idx)
            pairs.append((comment_ids[idx - 1], r))
        return pairs

    if len(objs) == n:
        logger.warning("Extraction response carried no ids; using positional mapping")
        return list(zip(comment_ids, objs))

    logger.warning(
        "Extraction response not safely attributable "
        f"({len(objs)} objects, no ids, {n} comments); skipping batch"
    )
    return []


def insert_indicators(
    conn: sqlite3.Connection,
    results: list[dict[str, Any]],
    batch_id: str,
    comment_ids: list[str],
) -> int:
    count = 0
    for cid, result in attribute_results(results, comment_ids):
        indicators = result.get("indicators", [])
        if isinstance(indicators, str):
            indicators = [indicators]
        for indicator in indicators:
            if is_stop_indicator(indicator):
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO comment_indicators "
                    "(comment_id, indicator, batch_id) VALUES (?, ?, ?)",
                    (cid, indicator, batch_id),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    return count


def run_extraction(
    conn: sqlite3.Connection,
    sample_size: int = EXTRACTION_SAMPLE_SIZE,
    batch_size: int = EXTRACTION_BATCH_SIZE,
    subreddit: str | None = None,
    model: str = OLLAMA_MODEL,
    base_url: str = OLLAMA_BASE_URL,
) -> None:
    persist_stop_indicators(conn)
    comment_ids = sample_opinion_comments(conn, size=sample_size, subreddit=subreddit)
    if not comment_ids:
        print("No opinion comments found to sample.")
        return

    batch_id = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT OR REPLACE INTO extraction_runs "
        "(batch_id, model, started_at, sample_size, comments_processed) "
        "VALUES (?, ?, ?, ?, 0)",
        (batch_id, model, time.strftime("%Y-%m-%dT%H:%M:%S"), len(comment_ids)),
    )
    conn.commit()

    already_processed = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT comment_id FROM comment_indicators WHERE batch_id = ?",
            (batch_id,),
        ).fetchall()
    }
    remaining = [cid for cid in comment_ids if cid not in already_processed]

    stop = False

    def handle_signal(sig, frame):
        nonlocal stop
        print("\nSIGINT received, finishing current batch...")
        stop = True

    original_handler = signal.signal(signal.SIGINT, handle_signal)

    total_processed = len(comment_ids) - len(remaining)
    total_batches = (len(remaining) + batch_size - 1) // batch_size

    print(f"Starting extraction: {len(remaining)} comments remaining in {total_batches} batches")
    print(f"Batch ID: {batch_id}, Model: {model}")

    warmup_ollama(model=model, base_url=base_url)

    for batch_idx in range(0, len(remaining), batch_size):
        if stop:
            break

        batch_ids = remaining[batch_idx : batch_idx + batch_size]
        comments = get_comments_by_ids(conn, batch_ids)
        if not comments:
            continue

        prompt = build_extraction_prompt(comments)
        try:
            # Scale output budget to the batch size (~120 tokens/comment of JSON)
            # so larger batches don't truncate the response and fail to parse.
            num_predict = max(500, batch_size * 128)
            response_text = call_ollama_with_retry(
                prompt, model=model, base_url=base_url, num_predict=num_predict
            )
        except Exception as e:
            logger.error(f"Ollama call failed after retries: {e}")
            continue

        results = parse_extraction_response(response_text)
        if results:
            # Attribute by the SAME order the prompt was numbered in (the order of
            # `comments`), not `batch_ids` — these can differ, which would shift
            # every cue onto the neighbouring comment.
            prompt_ids = [c["id"] for c in comments]
            n = insert_indicators(conn, results, batch_id, prompt_ids)
            total_processed += len(batch_ids)
            conn.execute(
                "UPDATE extraction_runs SET comments_processed = ? WHERE batch_id = ?",
                (total_processed, batch_id),
            )
            conn.commit()
            batch_num = batch_idx // batch_size + 1
            print(
                f"  Batch {batch_num}/{total_batches}: "
                f"{len(batch_ids)} comments, {n} indicators extracted"
            )

    conn.execute(
        "UPDATE extraction_runs SET completed_at = ? WHERE batch_id = ?",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), batch_id),
    )
    conn.commit()

    # Apply prior curation decisions to the freshly-extracted rows, so phrases you've
    # already categorised/merged don't come back as Uncategorised.
    cat_n, canon_n = backfill_categories(conn)
    conn.commit()
    print(
        f"Applied prior decisions to new rows: {cat_n:,} categorised, "
        f"{canon_n:,} canonical-linked."
    )

    signal.signal(signal.SIGINT, original_handler)
    print(f"Extraction complete. Batch ID: {batch_id}")


def backfill_categories(conn: sqlite3.Connection) -> tuple[int, int]:
    """Apply existing curation decisions to freshly-extracted (NULL-category) rows so a
    new sample doesn't re-surface phrases you've already decided. Each NULL row inherits
    the category its phrase already carries — from its other rows, else from a taxonomy
    seed — and rows for an aliased phrase get their canonical_indicator. Phrases never
    decided before stay uncategorised. Idempotent. Returns (categorised, canonical-linked).
    """
    # 1. Inherit the phrase's decided category from its existing categorised rows.
    n1 = conn.execute(
        "UPDATE comment_indicators AS ci SET category = src.cat, reviewed = 1 "
        "FROM (SELECT indicator, MAX(category) AS cat FROM comment_indicators "
        "      WHERE category IS NOT NULL GROUP BY indicator) AS src "
        "WHERE ci.category IS NULL AND ci.indicator = src.indicator"
    ).rowcount
    # 2. Remaining NULLs whose phrase is a taxonomy seed (a seed with no prior rows).
    n2 = conn.execute(
        "UPDATE comment_indicators AS ci SET category = t.category, reviewed = 1 "
        "FROM indicator_taxonomy AS t "
        "WHERE ci.category IS NULL AND ci.indicator = t.indicator_pattern "
        "AND t.category IS NOT NULL"
    ).rowcount
    # 3. canonical_indicator for new rows of aliased (merged) phrases.
    n3 = conn.execute(
        "UPDATE comment_indicators AS ci "
        "SET canonical_indicator = "
        "    (SELECT canonical FROM indicator_aliases a WHERE a.alias = ci.indicator) "
        "WHERE ci.canonical_indicator IS NULL "
        "AND ci.indicator IN (SELECT alias FROM indicator_aliases)"
    ).rowcount
    return n1 + n2, n3


def show_status(conn: sqlite3.Connection) -> None:
    runs = conn.execute(
        "SELECT batch_id, model, started_at, completed_at, sample_size, comments_processed "
        "FROM extraction_runs ORDER BY started_at DESC LIMIT 5"
    ).fetchall()
    if not runs:
        print("No extraction runs found.")
        return

    print(
        f"{'Batch ID':<12} {'Model':<15} {'Started':<20} "
        f"{'Completed':<20} {'Sample':>6} {'Processed':>10}"
    )
    print("-" * 95)
    for r in runs:
        completed = r[3] or "(in progress)"
        print(f"{r[0]:<12} {r[1]:<15} {r[2]:<20} {completed:<20} {r[4]:>6} {r[5]:>10}")

    total_indicators = conn.execute("SELECT COUNT(*) FROM comment_indicators").fetchone()[0]
    total_taxa = conn.execute("SELECT COUNT(*) FROM indicator_taxonomy").fetchone()[0]
    print(f"\nTotal indicators: {total_indicators:,}")
    print(f"Taxonomy entries: {total_taxa}")


TAXONOMY_BATCH_SIZE = 25


def build_taxonomy(
    conn: sqlite3.Connection,
    model: str = OLLAMA_MODEL,
    base_url: str = OLLAMA_BASE_URL,
) -> None:
    # Rank candidates on LLM-discovery rows ONLY. Semantic expansion writes the
    # seed phrase itself as `indicator`, so without this filter an established
    # seed's own expansion rows inflate its rank by orders of magnitude — seed
    # selection would feed on its own output. (LLM batches are uuid4[:8]; the
    # derived rows are batch_id 'semantic_*' / 'keyword_expansion_*'.)
    #
    # Also exclude curator-rejected phrases: the Curate UI records "this is not a
    # real cue" by DELETING the taxonomy row and stamping the phrase's comment
    # rows category='Noise' — so a Noise phrase has no taxonomy row for OR IGNORE
    # to protect, and without this clause a re-run would resurrect it as a seed
    # (verdict phrases are by construction the most frequent strings here).
    indicators = conn.execute(
        "SELECT indicator, COUNT(*) as c FROM comment_indicators "
        "WHERE LENGTH(indicator) > 2 "
        "AND batch_id NOT LIKE 'semantic_%' AND batch_id NOT LIKE 'keyword_%' "
        "AND indicator NOT IN ("
        "  SELECT DISTINCT indicator FROM comment_indicators WHERE category = 'Noise'"
        ") "
        "GROUP BY indicator ORDER BY c DESC LIMIT 200"
    ).fetchall()
    if not indicators:
        print("No indicators found. Run isthisai-extract sample first.")
        return

    warmup_ollama(model=model, base_url=base_url)

    total_count = 0
    total_batches = (len(indicators) + TAXONOMY_BATCH_SIZE - 1) // TAXONOMY_BATCH_SIZE

    for batch_idx in range(0, len(indicators), TAXONOMY_BATCH_SIZE):
        batch = indicators[batch_idx : batch_idx + TAXONOMY_BATCH_SIZE]
        batch_num = batch_idx // TAXONOMY_BATCH_SIZE + 1

        indicator_list = "\n".join([f"- {row[0]} ({row[1]}x)" for row in batch])
        prompt = (
            "Categorize each AI indicator below into a category "
            "and optional subcategory.\n"
            "Categories: " + ", ".join(TAXONOMY_CATEGORIES) + "\n\n"
            "Return ONLY a JSON array of objects with keys: "
            '"indicator", "category", "subcategory"\n\n'
            f"Indicators:\n{indicator_list}\n\nJSON:"
        )

        print(f"  Taxonomy batch {batch_num}/{total_batches}: {len(batch)} indicators...")
        response_text = call_ollama_with_retry(
            prompt, model=model, base_url=base_url, num_predict=4000
        )
        results = parse_extraction_response(response_text)
        if not results:
            results_fallback = _try_parse_json_object(response_text)
            if not results_fallback:
                logger.warning(f"Failed to parse taxonomy response for batch {batch_num}")
                continue
            results = results_fallback

        count = 0
        for item in results:
            pattern = (item.get("indicator") or "").strip()
            category = normalize_category(item.get("category"))
            subcategory = (item.get("subcategory") or "").strip()
            pattern = re.sub(r"\s*\(\d+x\)\s*$", "", pattern).strip()
            if not pattern or not category or is_stop_indicator(pattern):
                continue
            # OR IGNORE, not OR REPLACE: existing taxonomy rows are curated state
            # (recategorisations, merges' category writes). A re-run must only ADD
            # new patterns — never recategorise what a curator decided. (Curator
            # REJECTIONS are protected separately: the ranking query above excludes
            # phrases whose rows carry category='Noise', because rejection deletes
            # the taxonomy row and there is nothing here for OR IGNORE to keep.)
            conn.execute(
                "INSERT OR IGNORE INTO indicator_taxonomy "
                "(indicator_pattern, category, subcategory) "
                "VALUES (?, ?, ?)",
                (pattern, category, subcategory),
            )
            count += 1
        conn.commit()
        total_count += count
        print(f"    -> {count} patterns categorized")

    _backfill_categories(conn)
    print(
        f"Taxonomy built: {total_count} indicator patterns "
        f"categorized across {total_batches} batches."
    )

    category_counts = conn.execute(
        "SELECT category, COUNT(*) FROM indicator_taxonomy GROUP BY category ORDER BY COUNT(*) DESC"
    ).fetchall()
    for cat, cnt in category_counts:
        print(f"  {cat}: {cnt}")


def _try_parse_json_object(text: str) -> list[dict[str, Any]]:

    json_start = text.find("[")
    json_end = text.rfind("]") + 1
    if json_start == -1 or json_end == 0:
        return []
    try:
        return json.loads(text[json_start:json_end])
    except json.JSONDecodeError:
        return []


def _backfill_categories(conn: sqlite3.Connection) -> None:
    # Fill-only (category IS NULL), matching backfill_categories() above: rows
    # that already carry a category — whether stamped by a curator, semantic
    # expansion, or a previous run — must not be overwritten by a re-run.
    rows = conn.execute("SELECT indicator_pattern, category FROM indicator_taxonomy").fetchall()
    for pattern, category in rows:
        conn.execute(
            "UPDATE comment_indicators SET category = ? WHERE indicator = ? AND category IS NULL",
            (category, pattern),
        )
    conn.commit()


def expand_keywords(conn: sqlite3.Connection) -> None:
    taxonomy = conn.execute(
        "SELECT indicator_pattern, category, subcategory FROM indicator_taxonomy"
    ).fetchall()
    if not taxonomy:
        print("No taxonomy found. Run isthisai-extract taxonomy first.")
        return

    import re

    patterns = []
    for pattern, category, subcategory in taxonomy:
        escaped = re.escape(pattern.lower())
        patterns.append((pattern, category, subcategory, escaped))

    opinion_ids = get_opinion_comment_ids(conn)
    if not opinion_ids:
        print("No opinion comments found.")
        return

    processed_ids = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT comment_id "
            "FROM comment_indicators "
            "WHERE batch_id != 'keyword_expansion'"
        ).fetchall()
    }

    batch_id = f"keyword_expansion_{int(time.time())}"
    total_matches = 0
    batch_size = 1000

    for i in range(0, len(opinion_ids), batch_size):
        batch = opinion_ids[i : i + batch_size]
        placeholders = ",".join(["?"] * len(batch))
        comments = conn.execute(
            f"SELECT id, body FROM comments WHERE id IN ({placeholders})", batch
        ).fetchall()

        for cid, body in comments:
            if cid in processed_ids:
                continue
            if not body:
                continue
            body_lower = body.lower()
            for pattern, category, subcategory, regex_pattern in patterns:
                if re.search(regex_pattern, body_lower):
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
        pct = min(100, int((i + batch_size) / len(opinion_ids) * 100))
        print(f"  Progress: {pct}%", end="\r")

    print(
        f"\nKeyword expansion complete: {total_matches:,} indicator matches "
        f"across {len(opinion_ids):,} opinion comments."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="isthisai-extract",
        description="Extract AI indicators from comments using local LLM",
    )
    subparsers = parser.add_subparsers(dest="command", help="What to do")

    sample_parser = subparsers.add_parser(
        "sample", help="Run LLM extraction on a sample of comments"
    )
    sample_parser.add_argument("--size", type=int, default=EXTRACTION_SAMPLE_SIZE)
    sample_parser.add_argument("--subreddit", default=None)
    sample_parser.add_argument("--model", default=OLLAMA_MODEL)
    sample_parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    sample_parser.add_argument("--db-path", default=str(DB_PATH))

    taxonomy_parser = subparsers.add_parser(
        "taxonomy", help="Build indicator taxonomy from extracted indicators"
    )
    taxonomy_parser.add_argument("--model", default=OLLAMA_MODEL)
    taxonomy_parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    taxonomy_parser.add_argument("--db-path", default=str(DB_PATH))

    expand_parser = subparsers.add_parser("expand", help="Run keyword expansion using taxonomy")
    expand_parser.add_argument("--db-path", default=str(DB_PATH))

    subparsers.add_parser("status", help="Show extraction run status")

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
        if args.command == "sample":
            run_extraction(
                conn,
                sample_size=args.size,
                subreddit=args.subreddit,
                model=args.model,
                base_url=args.base_url,
            )
        elif args.command == "taxonomy":
            build_taxonomy(conn, model=args.model, base_url=args.base_url)
        elif args.command == "expand":
            expand_keywords(conn)
        elif args.command == "status":
            show_status(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
