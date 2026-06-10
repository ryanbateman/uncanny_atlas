# Setup Guide

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — package manager
- [Ollama](https://ollama.com) — for LLM extraction and embedding (must be running locally)

## Installation

```bash
# Install all extras (LLM, import, dev)
uv sync --all-extras

# Or install just core (collection + embedding)
uv sync
```

## Ollama Setup

Pull the required models (one-time):

```bash
ollama pull gemma3:4b         # for indicator extraction (use a REAL tag, not "gemma4:e4b")
ollama pull nomic-embed-text  # for semantic expansion (~274MB)
```

Verify Ollama is running and the models are present:

```bash
ollama list
```

### Running Ollama reliably (avoid generation stalls)

Extraction makes thousands of sequential LLM calls. On a memory-constrained GPU
(e.g. 8 GB) Ollama can intermittently **hang on a single generation** — it pins
the GPU and never returns, freezing the whole run — and the client socket timeout
does not reliably abort it. Root causes we hit, and how to avoid them:

| Symptom | Cause | Fix |
|---|---|---|
| Run wedges mid-batch; GPU ~80%, never returns | KV cache grows against the VRAM ceiling, or layers spill to CPU | **Pre-allocate a large context** and keep the model **fully GPU-resident** |
| Wedge right after killing a previous run | Degraded/reloaded model runner | Keep the model **pinned** (`keep_alive=-1`); don't rely on dynamic load/unload |
| Instant `HTTP 404` | Wrong model tag (`gemma4:e4b` placeholder) | Use a real tag, e.g. `gemma3:4b` |

Set these **once** (persist them, then **restart Ollama** so they apply at startup):

```powershell
# Windows (user-level); on Linux/macOS export them wherever `ollama serve` starts
setx OLLAMA_KEEP_ALIVE -1          # keep the model resident; no dynamic unload/reload
setx OLLAMA_NUM_PARALLEL 1         # single slot -> bounded, predictable KV cache (default ~4 multiplies it)
setx OLLAMA_MAX_LOADED_MODELS 1    # never evict the model for another
setx OLLAMA_FLASH_ATTENTION 1      # optional: lighter attention memory
setx OLLAMA_KV_CACHE_TYPE q8_0     # optional: halve KV-cache VRAM
```

Then **pin the model with a pre-allocated context** and make the pipeline request
the *same* context (`ISTHISAI_OLLAMA_NUM_CTX`), or Ollama silently reloads to the
4096 default and un-pins:

```powershell
# Pre-allocate a context that fills VRAM but stays FULLY on GPU.
# gemma3:4b on an 8 GB card: 98304 (~96k) is the max before it spills to CPU.
$body = '{"model":"gemma3:4b","keep_alive":-1,"options":{"num_ctx":98304}}'
Invoke-WebRequest http://localhost:11434/api/generate -Method Post -Body $body -ContentType application/json | Out-Null

$env:ISTHISAI_OLLAMA_MODEL   = "gemma3:4b"
$env:ISTHISAI_OLLAMA_NUM_CTX = "98304"   # MUST match the pinned context above
```

**Verify before any long run** — the model must be pinned and fully resident:

```bash
curl http://localhost:11434/api/ps
#   "size_vram" == "size"        -> fully on GPU (NOT partially offloaded to CPU)
#   "expires_at" far in future   -> pinned (keep_alive = -1)
# If size_vram < size, num_ctx is too large for VRAM -> lower it until fully resident.
```

## Full Pipeline

Run these commands in order to build the full dataset and analysis.

### Data Collection

```bash
# 1. Collect submissions from Reddit via PullPush API
uv run isthisai-collect submissions

# 2. Collect comments from Reddit via PullPush API
uv run isthisai-collect comments

# 3. Fill data gaps from Arctic Shift (if PullPush missed recent posts)
uv run isthisai-import api submissions
uv run isthisai-import api comments
```

### Stats & Validation

```bash
# 4. Print summary statistics about collected data
uv run isthisai-stats
uv run isthisai-stats --subreddit isthisAI
```

### LLM Extraction

Requires `gemma3:4b` running via Ollama (see "Running Ollama reliably" above).

```bash
# 5. Extract indicators from a random sample of 2,500 opinion comments
uv run isthisai-extract sample

# 6. Build taxonomy — categorise the top 200 most frequent indicators into the
#    8 taxonomy categories (curation can additionally flag entries as Noise)
uv run isthisai-extract taxonomy

# 7. Regex-based keyword expansion (optional; semantic expansion generally preferred)
uv run isthisai-extract expand

# Check extraction status
uv run isthisai-extract status
```

### Embedding & Semantic Expansion

Requires `nomic-embed-text` running via Ollama.

```bash
# 8. Embed taxonomy indicator patterns
uv run isthisai-embed indicators

# 9. Embed comments (resumable). Default: indicator-bearing only.
#    Add --all to embed the WHOLE corpus for maximal semantic coverage (hours; ~2.8 GB of vectors).
uv run isthisai-embed comments --all

# 10. Drop hallucinated LLM cues not supported by their comment (anti-hallucination)
uv run isthisai-embed ground            # add --dry-run to preview, --threshold 0.45 to tune

# 11. Match comment embeddings to taxonomy by cosine similarity
#     (default threshold 0.73 — lower values over-match; 0.65 historically made
#     generic seeds vacuum up hundreds of unrelated comments)
uv run isthisai-embed semantic

# 12. Show embedding coverage and source counts
uv run isthisai-embed status
```

### Web App

```bash
# 12. Launch the Explore + Curate web app
cd web && npm install && npm run dev   # http://localhost:5173
```

## CLI Reference

### Data Collection

| Command | Description |
|---|---|
| `isthisai-collect submissions` | Fetch submissions from PullPush API |
| `isthisai-collect comments` | Fetch comments from PullPush API |
| `isthisai-collect submissions --subreddit RealOrAI` | Fetch submissions for a specific subreddit |
| `isthisai-import api submissions` | Import submissions from Arctic Shift API |
| `isthisai-import api submissions --subreddit RealOrAI` | Import Arctic Shift data for a specific subreddit |

### Stats

| Command | Description |
|---|---|
| `isthisai-stats` | Print summary statistics |
| `isthisai-stats --subreddit isthisAI` | Print stats filtered by subreddit |

### LLM Extraction

| Command | Description |
|---|---|
| `isthisai-extract sample` | Run LLM extraction on a sample of opinion comments |
| `isthisai-extract sample --size 500` | Extract from 500 comments instead of default 2,500 |
| `isthisai-extract sample --subreddit isthisAI` | Extract from a specific subreddit |
| `isthisai-extract taxonomy` | Categorise extracted indicators into the taxonomy |
| `isthisai-extract expand` | Expand indicators via regex keyword matching |
| `isthisai-extract status` | Show extraction run history and indicator counts |

### Embedding & Semantic Expansion

| Command | Description |
|---|---|
| `isthisai-embed indicators` | Embed taxonomy indicator patterns |
| `isthisai-embed comments [--all]` | Embed comments (resumable); `--all` embeds the whole corpus for max semantic coverage |
| `isthisai-embed ground [--dry-run] [--threshold 0.45]` | Remove LLM cues not supported by their comment (anti-hallucination) |
| `isthisai-embed semantic --threshold 0.7` | Run semantic expansion with custom similarity threshold |
| `isthisai-embed status` | Show embedding coverage and source counts |

### Web App

| Command | Description |
|---|---|
| `cd web && npm run dev` | Launch the Explore + Curate web app (http://localhost:5173) |

## Environment Variables

Override defaults in `.env` or shell environment:

| Variable | Default | Description |
|---|---|---|
| `ISTHISAI_DB_PATH` | `data/isthisai.db` | SQLite database path |
| `ISTHISAI_SUBREDDIT` | `isthisAI` | Default subreddit |
| `ISTHISAI_OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `ISTHISAI_OLLAMA_MODEL` | `gemma3:4b` | LLM model for extraction (must be a real Ollama tag) |
| `ISTHISAI_OLLAMA_NUM_CTX` | `4096` | Context window; set high (e.g. `98304`) to pre-allocate the KV cache and avoid stalls — must match the pinned model |
| `ISTHISAI_OLLAMA_KEEP_ALIVE` | `10m` | How long Ollama keeps the model loaded; use `24h`/`-1` to pin it for a long run |
| `ISTHISAI_OLLAMA_TIMEOUT` | `600` | Ollama request timeout (seconds) |
| `ISTHISAI_EMBED_MODEL` | `nomic-embed-text` | Embedding model name |
| `ISTHISAI_EMBED_THRESHOLD` | `0.73` | Semantic expansion cosine similarity threshold |
| `ISTHISAI_EMBED_BATCH_SIZE` | `64` | Embedding batch size |

## Development

```bash
# Install dev dependencies (pytest, ruff)
uv sync --extra dev

# Run tests
make test

# Run linter
make lint
```

## Data

Reddit data is not included. Run the collection commands to populate `data/isthisai.db`. The `data/` directory is gitignored.

## Web App

Launch with `cd web && npm install && npm run dev` (http://localhost:5173). One SvelteKit app over the same SQLite DB, replacing the old Flask admin UI:

| View | Purpose |
|---|---|
| Explore → Overview / Indicators | Growth trends, indicator categories, sources, top indicators |
| Explore → Semantic matches | Audit embedding-based matches |
| Explore → Pipeline status | Extraction runs, embedding coverage, category distribution |
| Curate → Categorize | Bulk category corrections — one change backfills all matching rows |
| Curate → Taxonomy | Edit taxonomy patterns (affects future semantic expansion) |
| Curate → Merge | Merge near-duplicate phrases into a canonical indicator |