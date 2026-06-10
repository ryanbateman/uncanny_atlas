import os
from pathlib import Path

PULLPUSH_BASE_URL = os.environ.get("ISTHISAI_PULLPUSH_URL", "https://api.pullpush.io")
PULLPUSH_PAGE_SIZE = int(os.environ.get("ISTHISAI_PAGE_SIZE", "100"))
PULLPUSH_DELAY_SECONDS = float(os.environ.get("ISTHISAI_DELAY", "2.0"))
DEFAULT_SUBREDDIT = os.environ.get("ISTHISAI_SUBREDDIT", "isthisAI")
SUPPORTED_SUBREDDITS = ["isthisAI", "RealOrAI"]

MAX_RETRIES = int(os.environ.get("ISTHISAI_MAX_RETRIES", "5"))
INITIAL_RETRY_DELAY = float(os.environ.get("ISTHISAI_INITIAL_RETRY_DELAY", "2.0"))
MAX_RETRY_DELAY = float(os.environ.get("ISTHISAI_MAX_RETRY_DELAY", "60.0"))
REQUEST_TIMEOUT = float(os.environ.get("ISTHISAI_REQUEST_TIMEOUT", "30.0"))

DB_PATH = Path(os.environ.get("ISTHISAI_DB_PATH", str(Path("data") / "isthisai.db")))
CURRENT_SCHEMA_VERSION = 8

OLLAMA_BASE_URL = os.environ.get("ISTHISAI_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("ISTHISAI_OLLAMA_MODEL", "gemma3:4b")
# Context window. A large value pre-allocates the KV cache up front so a long
# generation can't grow it into a VRAM-pressure stall. Must match the value the
# model is loaded/pinned with, or Ollama reloads on the first request.
OLLAMA_NUM_CTX = int(os.environ.get("ISTHISAI_OLLAMA_NUM_CTX", "4096"))
EXTRACTION_BATCH_SIZE = int(os.environ.get("ISTHISAI_EXTRACTION_BATCH_SIZE", "5"))
EXTRACTION_SAMPLE_SIZE = int(os.environ.get("ISTHISAI_EXTRACTION_SAMPLE_SIZE", "2500"))
# Minimum comment length (chars) to be eligible for indicator extraction. Gates both
# the LLM candidate sample and semantic expansion — a one-word/emoji reaction is never
# describing a visual tell, so below this we don't read or match it.
MIN_COMMENT_LENGTH = int(os.environ.get("ISTHISAI_MIN_COMMENT_LENGTH", "20"))

OLLAMA_EMBED_MODEL = os.environ.get("ISTHISAI_EMBED_MODEL", "nomic-embed-text")
EMBEDDING_BATCH_SIZE = int(os.environ.get("ISTHISAI_EMBED_BATCH_SIZE", "64"))
EMBEDDING_SIMILARITY_THRESHOLD = float(os.environ.get("ISTHISAI_EMBED_THRESHOLD", "0.73"))
# Grounding: an LLM-extracted cue is kept only if its phrase embedding is at least
# this cosine-similar to its comment's embedding. Filters out hallucinated cues the
# text-only model invents for cue-less comments (e.g. "unnatural blinking" on a
# comment that never mentions eyes). Lower = more permissive.
GROUNDING_THRESHOLD = float(os.environ.get("ISTHISAI_GROUNDING_THRESHOLD", "0.45"))

OLLAMA_TIMEOUT = int(os.environ.get("ISTHISAI_OLLAMA_TIMEOUT", "600"))
# Ollama accepts keep_alive as a duration string ("10m") OR a number of seconds
# (-1 = keep resident forever). A bare numeric string like "-1" is NOT a valid
# duration and is rejected with a 400, so coerce numerics to int.
_keep_alive_raw = os.environ.get("ISTHISAI_OLLAMA_KEEP_ALIVE", "10m")
OLLAMA_KEEP_ALIVE: int | str = (
    int(_keep_alive_raw) if _keep_alive_raw.lstrip("-").isdigit() else _keep_alive_raw
)
