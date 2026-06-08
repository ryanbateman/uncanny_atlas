# Research: Visual Exploration of /r/isthisAI Growth

## Subreddit Profile

| Field | Value |
|---|---|
| Name | r/isthisAI |
| Created | May 2, 2023 (Unix: 1683021672) |
| Subscribers | ~248K (as of April 2026) |
| Type | Public |
| Description | "Ask whether or not a picture, video or anything is AI-generated" |
| Submission type | Any (links, images, videos, text) |

The subreddit emerged alongside the explosion of AI-generated content and has grown rapidly from 0 to ~248K subscribers in under 3 years — a compelling case study for community growth around an emerging cultural phenomenon.

---

## Data Sources

### 1. PullPush API (Recommended for historical data)

**URL**: https://api.pullpush.io/
**Status**: Operational (back online Oct 2025; has data up to ~May 2025)
**Auth**: None required
**Cost**: Free

The primary successor to the original Pushshift API. Provides historical Reddit submission and comment search with no authentication.

**Endpoints**:
- `GET /reddit/search/submission/` — search submissions by subreddit, date range, author, etc.
- `GET /reddit/search/comment/` — search comments
- `GET /reddit/submission/comment_ids/{id}` — get all comment IDs for a post

**Key parameters**: `subreddit`, `after`, `before` (epoch timestamps), `size` (1-1000), `sort`, `q` (full-text search)

**Limitations**:
- Data coverage has a gap after ~May 2025 (as of April 2026). Recent months may be incomplete.
- Max 1000 results per query; must paginate using `before`/`after` parameters
- Occasional downtime for maintenance

**Example query** (all submissions to r/isthisAI):
```
https://api.pullpush.io/reddit/search/submission/?subreddit=isthisAI&size=1000&sort=asc
```

**Python wrapper**: [pullpush-mcp](https://github.com/jacklenzotti/pullpush-mcp) (TypeScript MCP server) or use `requests` directly.

---

### 2. Arctic Shift (Recommended for bulk/dump data)

**URL**: https://github.com/ArthurHeitmann/arctic_shift
**Web interface**: https://arctic-shift.photon-reddit.com/
**Status**: Active, monthly dumps through Feb 2026
**Auth**: None for downloads; API has rate limits

Monthly dumps of all Reddit data in compressed NDJSON (.zst) format, available via Academic Torrents. Each month is ~50-60GB. Download the full dump and filter locally.

**Advantages**:
- Most complete historical coverage (2005–present)
- No rate limits on local processing
- Can filter any subreddit after download

**Limitations**:
- Large downloads (must download full month, then filter)
- Requires `zstandard` library in Python for decompression
- Web UI cannot do full-text search without specifying subreddit
- Cannot sort by score in web interface

**Processing**:
```bash
git clone --recursive https://github.com/ArthurHeitmann/arctic_shift.git
pip install zstandard
# Edit scripts/processFiles.py, add custom logic to processFile()
```

**Academic Torrents collection**: https://academictorrents.com/collection/datasetreddit — monthly dumps from 2005-06 through 2026-02.

---

### 3. Reddit Official API (via PRAW)

**Library**: `praw` (Python Reddit API Wrapper)
**Auth**: Requires Reddit app registration (free, non-commercial tier)
**Rate limit**: 100 queries/minute (free tier)

**Critical limitation**: Can only retrieve ~1,000 items from any listing endpoint (`new`, `hot`, `top`, etc.). This is a hard Reddit API limit. For /r/isthisAI with ~248K subscribers, this is likely insufficient for historical analysis.

**Good for**: Current metadata, recent posts, full comment trees on specific posts, real-time monitoring
**Bad for**: Historical data beyond 1,000 items, time-range queries (removed in API v6)

---

### 4. ScrapiReddit (No-auth alternative)

**URL**: https://github.com/rodneykeilson/ScrapiReddit
**Auth**: None required (scrapes public Reddit JSON endpoints)
**Install**: `pip install scrapi-reddit`

Still subject to ~1,000 item listing limit per endpoint. Useful for quick data pulls:
```bash
scrapi-reddit isthisAI --limit 200 --fetch-comments --output-format both
```

---

### 5. RedditHarbor (Systematic collection)

**URL**: https://github.com/socius-org/RedditHarbor
**Auth**: Requires Reddit API credentials + Supabase account
**Install**: `pip install redditharbor`

Designed for researchers. Collects into Supabase DB. Includes PII masking. Best for ongoing systematic collection.

---

### 6. Third-party stats sites

- **reddstats.com** — tracks subscriber counts for 850K+ subreddits with daily snapshots
- **freesubstats.com** — free subreddit analytics, growth tracking
- **subredditstats.com** — historical subscriber and activity trends

Can supplement with subscriber count time series that would otherwise require daily polling.

---

## Recommended Data Acquisition Strategy

For /r/isthisAI (created May 2023, ~248K subs):

### Phase 1: Historical data (May 2023 – May 2025) — PullPush API

1. Query submissions incrementally using `after`/`before` epoch timestamps
2. Collect all submission metadata (title, author, score, num_comments, created_utc, link_flair_text, etc.)
3. Query comments for each submission or collect comments separately with subreddit filter
4. Store in SQLite or CSV/Parquet

Estimated volume: with ~248K subscribers, likely thousands of posts and tens of thousands of comments. Manageable within PullPush pagination limits.

### Phase 2: Recent data (May 2025 – present) — Arctic Shift or PRAW

Since PullPush may have a data gap after May 2025:
- **Option A**: Download 2-3 monthly Arctic Shift dumps (~100-180GB total), filter for r/isthisAI locally
- **Option B**: Use PRAW to collect the most recent ~1,000 posts and their comment trees
- **Option C**: Check if PullPush has been updated (data coverage is improving)

### Phase 3: Ongoing collection

Set up PRAW or RedditHarbor to periodically scrape new submissions and comments.

---

## Data Schema

### Submissions
| Field | Source | Description |
|---|---|---|
| id | all | Reddit submission ID |
| title | all | Post title |
| author | all | Username (or [deleted]) |
| created_utc | all | Epoch timestamp |
| score | all | Net upvotes |
| num_comments | all | Comment count |
| upvote_ratio | API | Upvote percentage |
| link_flair_text | API/PullPush | Post flair/tag |
| is_video | API | Boolean |
| is_self | API | Is text post? |
| url | API | Media URL |
| selftext | API/PullPush | Body text |
| subreddit_subscribers | API | Sub count at access time |

### Comments
| Field | Source | Description |
|---|---|---|
| id | all | Comment ID |
| link_id | all | Parent submission ID |
| author | all | Username |
| body | all | Comment text |
| created_utc | all | Epoch timestamp |
| score | all | Net upvotes |
| parent_id | all | Parent comment or post ID |

### Labels (for text analysis — Phases 8-9)
| Field | Type | Description |
|---|---|---|
| id | TEXT PK | Comment or submission ID |
| label_type | TEXT NOT NULL | e.g. 'ai_tell', 'verdict', 'tell_category' |
| label_value | TEXT NOT NULL | e.g. 'fingers', 'is_ai', 'lighting' |
| confidence | REAL | Optional: model confidence |
| source | TEXT NOT NULL | 'manual', 'regex', 'gpt-4', 'classifier' |
| created_at | TEXT | DEFAULT CURRENT_TIMESTAMP |

This table is forward-compatible scaffolding — it costs nothing now but gives text analysis (Phases 8-9) a place to write results without migrating the schema.

---

## Visualization & Exploration Ideas

### Metric categories

1. **Submissions over time** — line/area chart, daily/weekly/monthly post volume
2. **Unique users over time** — distinct authors per period, new vs. returning
3. **Comment volume over time** — total comments per period, comments per post ratio
4. **Subscriber milestones** — overlay subscriber growth (from reddstats or Wayback Machine)
5. **Post type breakdown** — image/video/link/text distribution over time
6. **Flair/tag distribution** — how post categorization evolved
7. **Engagement ratios** — score per post, comments per post, upvote ratios over time
8. **Top posts** — all-time and by time period
9. **User activity distribution** — power-law visualization of poster frequency
10. **Growth event annotations** — correlate spikes with external events (AI model releases, viral posts)

### Text analysis metric categories (Phases 8-9)

11. **AI tell frequency over time** — which visual tells (fingers, teeth, lighting, artifacts, etc.) are mentioned most, and how that shifts
12. **Tell co-occurrence** — which tells are mentioned together in the same comment (e.g. "fingers + teeth")
13. **Verdict patterns** — distribution of "is AI" vs. "is not AI" vs. "unsure" over time
14. **Tell effectiveness** — do comments mentioning specific tells correlate with higher scores or more upvotes on the parent post?
15. **Language evolution** — how the vocabulary of AI detection has changed from 2023 to now
16. **Automated vs. manual tells** — comparing regex/keyword extraction vs. LLM-labeled tells for coverage and accuracy

### Technology stack options

| Stack | Pros | Cons |
|---|---|---|
| **Streamlit + Pandas** | Quickest to build; Python-native; interactive widgets | Limited customization; requires server |
| **D3.js + Vanilla JS** | Maximum flexibility; beautiful visualizations | More development time |
| **Observable/D3 notebooks** | Rapid prototyping; reactive data flow | Harder to self-host |
| **React + D3/recharts** | Full app; interactivity; component model | Heavier setup |
| **Jupyter + Plotly/matplotlib** | Familiar; good for exploration | Not an interactive web app |
| **Vega-Lite** | Declarative; easy to generate from data | Less flexible than D3 |

**Recommendation**: Start with **Streamlit** for rapid prototyping and data exploration, then optionally port the most compelling visualizations to **D3.js** or **Observable** for polish and interactivity.

---

## Notable Considerations

1. **Deleted/removed content**: PullPush and Arctic Shift may contain posts since deleted from Reddit. This is beneficial for historical analysis — higher coverage than live Reddit.

2. **Quick-deletion pattern**: Many users in /r/isthisAI delete posts after getting answers. Historical archives will have significantly higher coverage than the live subreddit.

3. **The 1,000-item limit**: The single biggest Reddit API constraint. For any historical analysis, you **must** use PullPush or Arctic Shift.

4. **Rate limiting**: PullPush has no published rate limits — be respectful (add delays). Reddit API is 100 QPM. Arctic Shift dumps have no limits (local processing).

5. **Comment trees**: PullPush returns flat comment lists without threading. For threaded data, combine PullPush for comment discovery with Reddit API for tree structure.

6. **Subscriber count history**: Reddit doesn't expose historical subscriber counts. reddstats.com may have snapshots. Alternatively, check Wayback Machine for /r/isthisAI pages over time.

7. **Ethics/TOS**: Reddit's 2023 API terms restrict commercial data use. For personal/academic research this is fine. PullPush operates in a gray area. Academic Torrents are widely used in published research.

8. **November 2025 change**: Reddit now requires admin approval for new API tokens. If you don't already have Reddit API credentials, getting them may be difficult. PullPush and Arctic Shift don't require Reddit credentials.

---

## Linked Plans

- [Phase 0: Repo Scaffolding — Detailed Plan](/doc/phase-0-repo-scaffolding-detailed-plan-7c0Ya84HFk) (Outline)
- [Phase 1: Submission & Comment Collection — Detailed Plan](/doc/phase-1-submission-comment-collection-detailed-plan-dMgaAebggh) (Outline)
- [Phase 2: Data Gap, Validation & Summary Stats — Detailed Plan](/doc/phase-2-data-gap-validation-summary-stats-detailed-plan-IhXCOrPl1R) (Outline)

---

## Next Steps

1. **Decide on tech stack** for visualization (Streamlit recommended for v1)
2. **Pull historical submissions** from PullPush for r/isthisAI (May 2023 – present)
3. **Pull historical comments** from PullPush
4. **Assess data gaps** — compare PullPush coverage against Reddit API recent posts
5. **Get subscriber count timeline** from reddstats.com or Wayback Machine
6. **Build exploratory visualizations** and iterate based on what's interesting
7. **Refine into an interactive exploration tool** with time range selectors, metric toggles, and event annotations
8. **Tell extraction** — label comments with AI detection tells and verdict patterns (Phase 8)
9. **Text analysis dashboard** — visualize tell frequency, co-occurrence, and verdict patterns over time (Phase 9)