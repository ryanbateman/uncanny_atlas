import { sqlite, prep } from './db';
import { AI_EVENTS } from '$lib/aiTimeline';

/**
 * Analytical (read-only) queries ported from src/isthisai/queries.py.
 * Returns plain objects instead of pandas DataFrames. (Verdict has been removed
 * from the pipeline entirely — there is no verdict column.)
 *
 * Indicator-level groupings resolve aliases so merged phrases collapse to their
 * canonical form. See CANONICAL_SQL / canonical-resolution in curate.ts.
 */

const GRANULARITY_FORMATS: Record<string, string> = {
	day: '%Y-%m-%d',
	week: '%Y-W%W',
	month: '%Y-%m'
};

type Clause = { sql: string; params: unknown[] };

function dateFilter(start?: string, end?: string, column = 'created_utc'): Clause {
	const parts: string[] = [];
	const params: unknown[] = [];
	if (start) {
		parts.push(`${column} >= strftime('%s', ?, 'utc')`);
		params.push(start);
	}
	if (end) {
		parts.push(`${column} < strftime('%s', ?, 'utc', '+1 day')`);
		params.push(end);
	}
	return { sql: parts.join(' AND '), params };
}

function flairFilter(flairs?: string[], prefix = ''): Clause {
	if (!flairs || flairs.length === 0) return { sql: '', params: [] };
	const NONE = '(none)';
	const hasNone = flairs.includes(NONE);
	const regular = flairs.filter((f) => f !== NONE);
	const parts: string[] = [];
	const params: unknown[] = [];
	if (regular.length) {
		parts.push(`${prefix}link_flair_text IN (${regular.map(() => '?').join(', ')})`);
		params.push(...regular);
	}
	if (hasNone) parts.push(`${prefix}link_flair_text IS NULL`);
	if (!parts.length) return { sql: '', params: [] };
	return { sql: parts.length > 1 ? `(${parts.join(' OR ')})` : parts[0], params };
}

function subredditFilter(subreddit?: string, prefix = ''): Clause {
	if (subreddit) return { sql: `${prefix}subreddit = ?`, params: [subreddit] };
	return { sql: '', params: [] };
}

function buildWhere(...clauses: Clause[]): Clause {
	const parts: string[] = [];
	const params: unknown[] = [];
	for (const c of clauses) {
		if (c.sql) {
			parts.push(`(${c.sql})`);
			params.push(...c.params);
		}
	}
	if (!parts.length) return { sql: '', params: [] };
	return { sql: `WHERE ${parts.join(' AND ')}`, params };
}

function fmtOf(granularity: string, fallback = '%Y-%m-%d'): string {
	return GRANULARITY_FORMATS[granularity] ?? fallback;
}

/**
 * SQL expression returning the ISO start date (YYYY-MM-DD) of the bucket a
 * unix-epoch timestamp falls in, for the given granularity. Using a real date
 * (not a `%Y-W%W` label) lets the charts plot on a continuous time axis with no
 * gaps, and lets weekly buckets align to ISO Mondays.
 */
function bucketStartSql(granularity: string, col = 'created_utc'): string {
	const t = `${col}, 'unixepoch'`;
	if (granularity === 'month') return `strftime('%Y-%m-01', ${t})`;
	if (granularity === 'day') return `date(${t})`;
	// week → Monday of the ISO week (strftime %w: 0=Sun..6=Sat)
	return `date(${t}, '-' || ((strftime('%w', ${t}) + 6) % 7) || ' days')`;
}

/** Earliest/latest activity across BOTH submissions and comments (unix secs). */
export function overTimeBounds(): { min: number; max: number } | null {
	// Separate MIN/MAX per table so each is an O(1) index lookup on created_utc.
	// A single `SELECT MIN(x), MAX(x)` can't use the index for both aggregates at
	// once, so it would full-scan the 912k-row comments table — and this runs a
	// few times per page load.
	const one = (sql: string) => (prep(sql).get() as { c: number | null }).c;
	const mins = [
		one('SELECT MIN(created_utc) AS c FROM submissions'),
		one('SELECT MIN(created_utc) AS c FROM comments')
	].filter((v): v is number => v != null);
	const maxs = [
		one('SELECT MAX(created_utc) AS c FROM submissions'),
		one('SELECT MAX(created_utc) AS c FROM comments')
	].filter((v): v is number => v != null);
	if (!mins.length || !maxs.length) return null;
	return { min: Math.min(...mins), max: Math.max(...maxs) };
}

/** ISO date (UTC) of a unix-epoch second. */
function isoDay(unix: number): string {
	return new Date(unix * 1000).toISOString().slice(0, 10);
}

/** ISO date of the earliest tracked AI release — anchors the timeline start. */
const EARLIEST_EVENT = AI_EVENTS.reduce(
	(m, e) => (e.date < m ? e.date : m),
	AI_EVENTS[0]?.date ?? '9999-12-31'
);

/**
 * Shared over-time axis bounds. The START is extended back to the earliest
 * tracked AI release when it predates the first data point, so e.g. Stable
 * Diffusion (released 8 days before the first submission) still anchors the
 * timeline; the END is the latest activity.
 */
function effectiveBounds(): { minUnix: number; maxUnix: number; minIso: string; maxIso: string } | null {
	const b = overTimeBounds();
	if (!b) return null;
	const dataMinIso = isoDay(b.min);
	const minIso = EARLIEST_EVENT < dataMinIso ? EARLIEST_EVENT : dataMinIso;
	const minUnix = Math.floor(Date.parse(minIso + 'T00:00:00Z') / 1000);
	return { minUnix, maxUnix: b.max, minIso, maxIso: isoDay(b.max) };
}

/**
 * Contiguous bucket axis (ISO start dates) spanning the shared range — every
 * bucket from first to last, gaps included. Both over-time charts densify
 * against this so they share an identical, gap-free time axis starting at the
 * earliest tracked event (or first activity, whichever is earlier).
 */
export function contiguousBuckets(granularity = 'week'): string[] {
	const b = effectiveBounds();
	if (!b) return [];
	let expr: string;
	if (granularity === 'month') expr = `strftime('%Y-%m-01', day)`;
	else if (granularity === 'day') expr = `date(day)`;
	else expr = `date(day, '-' || ((strftime('%w', day) + 6) % 7) || ' days')`;
	return (
		sqlite
			.prepare(
				`WITH RECURSIVE d(day) AS (
					SELECT date(?, 'unixepoch')
					UNION ALL SELECT date(day, '+1 day') FROM d WHERE day < date(?, 'unixepoch')
				) SELECT DISTINCT ${expr} AS p FROM d ORDER BY p`
			)
			.all(b.minUnix, b.maxUnix) as { p: string }[]
	).map((r) => r.p);
}

/** Min/max of the shared axis as ISO dates, for the Plot x-scale domain. */
export function overTimeDomain(): { min: string; max: string } | null {
	const b = effectiveBounds();
	return b ? { min: b.minIso, max: b.maxIso } : null;
}

/**
 * ISO date (UTC) of the earliest comment on any tracked subreddit — marked as a
 * vertical line on the over-time charts. The axis can start earlier (it's
 * extended back to the first tracked AI release), so this sits inside the range.
 * Null when there are no comments.
 */
export function firstCommentDate(): string | null {
	const c = (prep('SELECT MIN(created_utc) AS c FROM comments').get() as { c: number | null }).c;
	return c == null ? null : isoDay(c);
}

/** ISO date (UTC) of the earliest submission on any tracked subreddit — the
 *  companion milestone marker to firstCommentDate(). Null when none. */
export function firstSubmissionDate(): string | null {
	const c = (prep('SELECT MIN(created_utc) AS c FROM submissions').get() as { c: number | null }).c;
	return c == null ? null : isoDay(c);
}

/**
 * AI-release events for the over-time charts, placed at their exact date on the
 * continuous time axis. Events outside the shared range are dropped. `kind` is
 * the modality, `release` how it shipped.
 */
export function timelineMarkers() {
	const b = effectiveBounds();
	if (!b) return [];
	return AI_EVENTS.filter((ev) => ev.date >= b.minIso && ev.date <= b.maxIso).map((ev) => ({
		date: ev.date,
		label: ev.label,
		kind: ev.kind,
		release: ev.release
	}));
}

/** Indicator filters operate on the comments join (alias c) + indicator alias ci. */
function indicatorWhere(opts: IndicatorOpts): Clause {
	const parts: string[] = [];
	const params: unknown[] = [];
	if (opts.startDate) {
		parts.push("c.created_utc >= strftime('%s', ?, 'utc')");
		params.push(opts.startDate);
	}
	if (opts.endDate) {
		parts.push("c.created_utc < strftime('%s', ?, 'utc', '+1 day')");
		params.push(opts.endDate);
	}
	if (opts.subreddit) {
		parts.push('c.subreddit = ?');
		params.push(opts.subreddit);
	}
	if (opts.excludeNoise) parts.push("ci.category != 'Noise'");
	return { sql: parts.length ? `WHERE ${parts.join(' AND ')}` : '', params };
}

/** Canonical phrase: alias-resolved indicator. Used wherever we group by phrase. */
export const CANONICAL_SQL =
	'COALESCE(a.canonical, ci.canonical_indicator, ci.indicator)';
const CANONICAL_JOIN = 'LEFT JOIN indicator_aliases a ON a.alias = ci.indicator';

/**
 * Read-only merge map for Explore badges: each canonical with the alias phrases
 * folded into it. Derived purely from indicator_aliases so Explore loads need no
 * dependency on the write module (curate.ts). Cheaper than curate's listMerges()
 * (no per-phrase usage) — the badge needs only the member names.
 */
export function mergeGroups(): { canonical: string; members: string[] }[] {
	const rows = prep(
		'SELECT alias, canonical FROM indicator_aliases ORDER BY canonical, alias'
	).all() as { alias: string; canonical: string }[];
	const byCanonical = new Map<string, string[]>();
	for (const { alias, canonical } of rows) {
		const arr = byCanonical.get(canonical) ?? [];
		arr.push(alias);
		byCanonical.set(canonical, arr);
	}
	return [...byCanonical.entries()].map(([canonical, members]) => ({ canonical, members }));
}

// ---- shared option types ------------------------------------------------

interface BaseOpts {
	startDate?: string;
	endDate?: string;
	subreddit?: string;
}
interface FlairOpts extends BaseOpts {
	flairs?: string[];
}
interface IndicatorOpts extends BaseOpts {
	excludeNoise?: boolean;
}

// ---- time series --------------------------------------------------------

export function submissionsOverTime(o: FlairOpts & { granularity?: string } = {}) {
	const fmt = fmtOf(o.granularity ?? 'day');
	const w = buildWhere(dateFilter(o.startDate, o.endDate), flairFilter(o.flairs), subredditFilter(o.subreddit));
	return sqlite
		.prepare(
			`SELECT strftime('${fmt}', created_utc, 'unixepoch') AS period, COUNT(*) AS count ` +
				`FROM submissions ${w.sql} GROUP BY period ORDER BY period`
		)
		.all(...w.params) as { period: string; count: number }[];
}

export function commentsOverTime(o: BaseOpts & { granularity?: string } = {}) {
	const fmt = fmtOf(o.granularity ?? 'day');
	const w = buildWhere(dateFilter(o.startDate, o.endDate), subredditFilter(o.subreddit));
	return sqlite
		.prepare(
			`SELECT strftime('${fmt}', created_utc, 'unixepoch') AS period, COUNT(*) AS count ` +
				`FROM comments ${w.sql} GROUP BY period ORDER BY period`
		)
		.all(...w.params) as { period: string; count: number }[];
}

export function submissionsOverTimeBySubreddit(o: BaseOpts & { granularity?: string } = {}) {
	const period = bucketStartSql(o.granularity ?? 'day');
	const w = buildWhere(dateFilter(o.startDate, o.endDate));
	return sqlite
		.prepare(
			`SELECT ${period} AS period, subreddit, COUNT(*) AS count ` +
				`FROM submissions ${w.sql} GROUP BY period, subreddit ORDER BY period, subreddit`
		)
		.all(...w.params) as { period: string; subreddit: string; count: number }[];
}

export function commentsOverTimeBySubreddit(o: BaseOpts & { granularity?: string } = {}) {
	const period = bucketStartSql(o.granularity ?? 'day');
	const w = buildWhere(dateFilter(o.startDate, o.endDate));
	return sqlite
		.prepare(
			`SELECT ${period} AS period, subreddit, COUNT(*) AS count ` +
				`FROM comments ${w.sql} GROUP BY period, subreddit ORDER BY period, subreddit`
		)
		.all(...w.params) as { period: string; subreddit: string; count: number }[];
}

export function flairOverTime(o: FlairOpts & { granularity?: string } = {}) {
	const fmt = fmtOf(o.granularity ?? 'day');
	const w = buildWhere(dateFilter(o.startDate, o.endDate), flairFilter(o.flairs), subredditFilter(o.subreddit));
	return sqlite
		.prepare(
			`SELECT strftime('${fmt}', created_utc, 'unixepoch') AS period, ` +
				`COALESCE(link_flair_text, '(none)') AS flair, COUNT(*) AS count ` +
				`FROM submissions ${w.sql} GROUP BY period, flair ORDER BY period, flair`
		)
		.all(...w.params) as { period: string; flair: string; count: number }[];
}

// ---- distributions ------------------------------------------------------

export function flairDistribution(o: FlairOpts = {}) {
	const w = buildWhere(dateFilter(o.startDate, o.endDate), flairFilter(o.flairs), subredditFilter(o.subreddit));
	return sqlite
		.prepare(
			`SELECT COALESCE(link_flair_text, '(none)') AS flair, COUNT(*) AS count ` +
				`FROM submissions ${w.sql} GROUP BY flair ORDER BY count DESC`
		)
		.all(...w.params) as { flair: string; count: number }[];
}

const SCORE_BUCKETS: [number, number, string][] = [
	[-100, -1, '<0'],
	[0, 0, '0'],
	[1, 5, '1-5'],
	[6, 10, '6-10'],
	[11, 25, '11-25'],
	[26, 50, '26-50'],
	[51, 100, '51-100'],
	[101, 500, '101-500'],
	[501, 10000, '>500']
];

export function scoreDistribution(o: FlairOpts = {}) {
	const w = buildWhere(dateFilter(o.startDate, o.endDate), flairFilter(o.flairs), subredditFilter(o.subreddit));
	const cases = SCORE_BUCKETS.map(([lo, hi, label]) => `WHEN score BETWEEN ${lo} AND ${hi} THEN '${label}'`).join(' ');
	return sqlite
		.prepare(
			`SELECT CASE ${cases} END AS score_bucket, COUNT(*) AS count ` +
				`FROM submissions ${w.sql} GROUP BY score_bucket ORDER BY MIN(score)`
		)
		.all(...w.params) as { score_bucket: string; count: number }[];
}

export function submissionTypeBreakdown(o: FlairOpts = {}) {
	const w = buildWhere(dateFilter(o.startDate, o.endDate), flairFilter(o.flairs), subredditFilter(o.subreddit));
	return sqlite
		.prepare(
			`SELECT CASE WHEN is_video = 1 THEN 'video' WHEN is_self = 1 THEN 'text' ELSE 'link' END AS type, ` +
				`COUNT(*) AS count FROM submissions ${w.sql} GROUP BY type ORDER BY count DESC`
		)
		.all(...w.params) as { type: string; count: number }[];
}

/**
 * Submission-type composition (video / text / link) per time bucket — the media
 * mix over time, notably video's rise. Same is_video/is_self scheme as
 * submissionTypeBreakdown; 'link' is predominantly image posts (external links).
 */
export function submissionTypeOverTime(o: BaseOpts & { granularity?: string } = {}) {
	const period = bucketStartSql(o.granularity ?? 'day');
	const w = buildWhere(dateFilter(o.startDate, o.endDate));
	return sqlite
		.prepare(
			`SELECT ${period} AS period, ` +
				`CASE WHEN is_video = 1 THEN 'video' WHEN is_self = 1 THEN 'text' ELSE 'link' END AS type, ` +
				`COUNT(*) AS count FROM submissions ${w.sql} GROUP BY period, type ORDER BY period, type`
		)
		.all(...w.params) as { period: string; type: string; count: number }[];
}

export function coverageCalendar(subreddit?: string) {
	const w = buildWhere(subredditFilter(subreddit));
	return sqlite
		.prepare(
			`SELECT DATE(created_utc, 'unixepoch') AS date, COUNT(*) AS count ` +
				`FROM submissions ${w.sql} GROUP BY date ORDER BY date`
		)
		.all(...w.params) as { date: string; count: number }[];
}

export function dateRange(subreddit?: string): { min: string | null; max: string | null } {
	const w = buildWhere(subredditFilter(subreddit));
	const row = sqlite
		.prepare(
			`SELECT MIN(DATE(created_utc, 'unixepoch')) AS min, MAX(DATE(created_utc, 'unixepoch')) AS max ` +
				`FROM submissions ${w.sql}`
		)
		.get(...w.params) as { min: string | null; max: string | null } | undefined;
	return row?.min ? row : { min: null, max: null };
}

export function distinctFlairs(subreddit?: string): string[] {
	const w = buildWhere(subredditFilter(subreddit));
	const rows = sqlite
		.prepare(
			`SELECT DISTINCT COALESCE(link_flair_text, '(none)') AS flair FROM submissions ${w.sql} ORDER BY link_flair_text`
		)
		.all(...w.params) as { flair: string }[];
	return rows.map((r) => r.flair);
}

export function distinctSubreddits(): string[] {
	const rows = sqlite
		.prepare('SELECT DISTINCT subreddit FROM submissions ORDER BY subreddit')
		.all() as { subreddit: string }[];
	return rows.map((r) => r.subreddit);
}

export function totalCounts(subreddit?: string) {
	const w = buildWhere(subredditFilter(subreddit));
	const join = w.sql ? `${w.sql} AND` : 'WHERE';
	const subs = prep(`SELECT COUNT(*) AS c FROM submissions ${w.sql}`).get(...w.params) as { c: number };
	const coms = prep(`SELECT COUNT(*) AS c FROM comments ${w.sql}`).get(...w.params) as { c: number };
	const submitters = sqlite
		.prepare(`SELECT COUNT(DISTINCT author) AS c FROM submissions ${join} author IS NOT NULL`)
		.get(...w.params) as { c: number };
	const commenters = sqlite
		.prepare(`SELECT COUNT(DISTINCT author) AS c FROM comments ${join} author IS NOT NULL`)
		.get(...w.params) as { c: number };
	return {
		submissions: subs.c,
		comments: coms.c,
		uniqueSubmitters: submitters.c,
		uniqueCommenters: commenters.c
	};
}

export function topSubmissions(o: FlairOpts & { sortBy?: string; limit?: number } = {}) {
	const valid = new Set(['score', 'num_comments', 'upvote_ratio', 'created_utc']);
	const sortCol = o.sortBy && valid.has(o.sortBy) ? o.sortBy : 'score';
	const w = buildWhere(dateFilter(o.startDate, o.endDate), flairFilter(o.flairs), subredditFilter(o.subreddit));
	return sqlite
		.prepare(
			`SELECT id, title, author, score, num_comments, created_utc, ` +
				`COALESCE(link_flair_text, '(none)') AS flair, COALESCE(permalink, '') AS permalink ` +
				`FROM submissions ${w.sql} ORDER BY ${sortCol} DESC LIMIT ?`
		)
		.all(...w.params, o.limit ?? 25);
}

export function topAuthors(o: BaseOpts & { limit?: number } = {}) {
	const date = dateFilter(o.startDate, o.endDate);
	const sub = subredditFilter(o.subreddit);
	const parts: string[] = [];
	const params: unknown[] = [];
	if (date.sql) {
		parts.push(date.sql);
		params.push(...date.params);
	}
	parts.push('author IS NOT NULL');
	if (sub.sql) {
		parts.push(sub.sql);
		params.push(...sub.params);
	}
	return sqlite
		.prepare(
			`SELECT author, COUNT(*) AS submission_count, SUM(score) AS total_score, ROUND(AVG(score), 1) AS avg_score ` +
				`FROM submissions WHERE ${parts.join(' AND ')} GROUP BY author ORDER BY submission_count DESC LIMIT ?`
		)
		.all(...params, o.limit ?? 20);
}

// ---- indicators (canonical-resolved) ------------------------------------

export function indicatorCategoryCounts(o: IndicatorOpts = {}) {
	const w = indicatorWhere(o);
	return sqlite
		.prepare(
			`SELECT COALESCE(ci.category, 'Uncategorized') AS category, COUNT(*) AS count ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${w.sql} ` +
				`GROUP BY ci.category ORDER BY count DESC`
		)
		.all(...w.params) as { category: string; count: number }[];
}

export function indicatorsOverTime(
	o: IndicatorOpts & { granularity?: string; dedupeByPost?: boolean } = {}
) {
	const period = bucketStartSql(o.granularity ?? 'month', 'c.created_utc');
	const w = indicatorWhere(o);
	// Default counts mentions (rows); dedupe counts distinct posts per period.
	const cnt = o.dedupeByPost ? 'COUNT(DISTINCT c.link_id)' : 'COUNT(*)';
	return sqlite
		.prepare(
			`SELECT ${period} AS period, ` +
				`COALESCE(ci.category, 'Uncategorized') AS category, ${cnt} AS count ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${w.sql} ` +
				`GROUP BY period, category ORDER BY period, category`
		)
		.all(...w.params) as { period: string; category: string; count: number }[];
}

/**
 * The overall top-N indicators (by total distinct comments) plotted over time.
 *
 * We pick the N most-cited canonical cues across the whole range, then return a
 * dense series (each cue 0-filled in every period) so each draws a continuous
 * trend. Returns the series, the indicator order (by overall total), and the
 * period axis.
 */
export function topIndicatorsOverTime(
	o: IndicatorOpts & { granularity?: string; topN?: number; dedupeByPost?: boolean } = {}
) {
	const period = bucketStartSql(o.granularity ?? 'month', 'c.created_utc');
	const w = indicatorWhere(o);
	const topN = o.topN ?? 10;
	// Default counts distinct comments; dedupe counts distinct posts per period.
	const cnt = o.dedupeByPost ? 'COUNT(DISTINCT c.link_id)' : 'COUNT(DISTINCT ci.comment_id)';
	const raw = sqlite
		.prepare(
			`SELECT ${period} AS period, ` +
				`${CANONICAL_SQL} AS indicator, ${cnt} AS count ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${CANONICAL_JOIN} ${w.sql} ` +
				`GROUP BY period, ${CANONICAL_SQL}`
		)
		.all(...w.params) as { period: string; indicator: string; count: number }[];

	// Overall top-N by total distinct comments (periods are disjoint, so summing
	// per-period distinct counts gives the true total per cue).
	const totals = new Map<string, number>();
	for (const r of raw) totals.set(r.indicator, (totals.get(r.indicator) ?? 0) + r.count);
	const indicators = [...totals.entries()]
		.sort((a, b) => b[1] - a[1])
		.slice(0, topN)
		.map((e) => e[0]);
	const keep = new Set(indicators);

	// Densify over the shared contiguous axis (fixed start, no gaps) so the top
	// chart aligns with the other over-time charts.
	const periods = contiguousBuckets(o.granularity ?? 'month');
	const have = new Map<string, Map<string, number>>();
	for (const r of raw) {
		if (!keep.has(r.indicator)) continue;
		const m = have.get(r.period) ?? new Map<string, number>();
		m.set(r.indicator, r.count);
		have.set(r.period, m);
	}
	const series: { period: string; indicator: string; count: number }[] = [];
	for (const p of periods)
		for (const ind of indicators)
			series.push({ period: p, indicator: ind, count: have.get(p)?.get(ind) ?? 0 });
	return { series, indicators, periods };
}

export function indicatorsBySubreddit(o: IndicatorOpts = {}) {
	const w = indicatorWhere(o);
	return sqlite
		.prepare(
			`SELECT COALESCE(ci.category, 'Uncategorized') AS category, c.subreddit, COUNT(*) AS count ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${w.sql} ` +
				`GROUP BY ci.category, c.subreddit ORDER BY ci.category, c.subreddit`
		)
		.all(...w.params) as { category: string; subreddit: string; count: number }[];
}

export function indicatorSourceCounts(o: IndicatorOpts = {}) {
	const w = indicatorWhere(o);
	return sqlite
		.prepare(
			`SELECT CASE WHEN ci.batch_id LIKE 'semantic_%' THEN 'Semantic' ` +
				`WHEN ci.batch_id LIKE 'keyword_expansion%' THEN 'Keyword Expansion' ELSE 'LLM Extraction' END AS source, ` +
				`COUNT(*) AS count FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${w.sql} ` +
				`GROUP BY source ORDER BY count DESC`
		)
		.all(...w.params) as { source: string; count: number }[];
}

/**
 * Top individual indicator phrases, alias-resolved so merges collapse.
 * Counts DISTINCT comments per cue, so the figure is exactly "comments citing it".
 */
export function topIndicators(o: IndicatorOpts & { limit?: number } = {}) {
	const w = indicatorWhere(o);
	return sqlite
		.prepare(
			`SELECT ${CANONICAL_SQL} AS indicator, COALESCE(MAX(ci.category), 'Uncategorized') AS category, ` +
				`COUNT(DISTINCT ci.comment_id) AS count ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${CANONICAL_JOIN} ${w.sql} ` +
				`GROUP BY ${CANONICAL_SQL} ORDER BY count DESC LIMIT ?`
		)
		.all(...w.params, o.limit ?? 50) as { indicator: string; category: string; count: number }[];
}

export function indicatorCategories(): string[] {
	const rows = sqlite
		.prepare("SELECT DISTINCT category FROM comment_indicators WHERE category IS NOT NULL ORDER BY category")
		.all() as { category: string }[];
	return rows.map((r) => r.category);
}

export function indicatorExampleComments(category: string, limit = 10) {
	// One row per comment — a comment may cite several indicators in the same
	// category, so aggregate the (canonical) phrases instead of duplicating it.
	return sqlite
		.prepare(
			`SELECT c.id, c.body, c.author, c.score, c.subreddit, ` +
				`GROUP_CONCAT(DISTINCT ${CANONICAL_SQL}) AS indicator ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${CANONICAL_JOIN} ` +
				`WHERE ci.category = ? GROUP BY c.id ORDER BY c.score DESC LIMIT ?`
		)
		.all(category, limit) as {
		id: string;
		body: string;
		author: string | null;
		score: number | null;
		subreddit: string;
		indicator: string;
	}[];
}

// ---- explore: inspect one indicator -------------------------------------

/**
 * Canonical indicators with their distinct-comment counts, for the picker.
 * Capped to the most-cited ones (the long tail is singletons); the input is
 * free-text, so any exact name can still be typed even if not suggested.
 * Noise-tagged indicators are excluded unless `includeNoise` is set.
 */
export function indicatorChoices(limit = 1000, includeNoise = false) {
	const noiseClause = includeNoise ? '' : `AND COALESCE(MAX(ci.category), '') <> 'Noise'`;
	return sqlite
		.prepare(
			`SELECT ${CANONICAL_SQL} AS indicator, COUNT(DISTINCT ci.comment_id) AS comments ` +
				`FROM comment_indicators ci ${CANONICAL_JOIN} ` +
				`GROUP BY ${CANONICAL_SQL} HAVING comments >= 2 ${noiseClause} ORDER BY comments DESC, indicator LIMIT ?`
		)
		.all(limit) as { indicator: string; comments: number }[];
}

/**
 * Every comment that cites a given canonical indicator (alias-resolved), with
 * the raw phrase(s) that matched and how each was found.
 */
export function commentsForIndicator(indicator: string, o: { limit?: number; offset?: number } = {}) {
	const where = `WHERE ${CANONICAL_SQL} = ?`;
	const total = sqlite
		.prepare(`SELECT COUNT(DISTINCT ci.comment_id) AS c FROM comment_indicators ci ${CANONICAL_JOIN} ${where}`)
		.get(indicator) as { c: number };
	const rows = sqlite
		.prepare(
			`SELECT c.id, c.body, c.subreddit, c.score, ` +
				`GROUP_CONCAT(DISTINCT ci.indicator) AS matched, ` +
				`GROUP_CONCAT(DISTINCT CASE ` +
				`WHEN ci.batch_id LIKE 'semantic_%' THEN 'semantic' ` +
				`WHEN ci.batch_id LIKE 'keyword_%' THEN 'keyword' ELSE 'llm' END) AS sources ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${CANONICAL_JOIN} ${where} ` +
				`GROUP BY c.id ORDER BY c.score DESC, c.id LIMIT ? OFFSET ?`
		)
		.all(indicator, o.limit ?? 200, o.offset ?? 0) as {
		id: string;
		body: string;
		subreddit: string;
		score: number | null;
		matched: string;
		sources: string;
	}[];
	return { rows, total: total.c };
}

// ---- explore: semantic matches audit (read-only) ------------------------

export function semanticMatches(o: { category?: string; search?: string; limit?: number; offset?: number } = {}) {
	const parts = ["ci.batch_id LIKE 'semantic_%'"];
	const params: unknown[] = [];
	if (o.category) {
		parts.push('ci.category = ?');
		params.push(o.category);
	}
	if (o.search) {
		parts.push('(ci.indicator LIKE ? OR c.body LIKE ?)');
		params.push(`%${o.search}%`, `%${o.search}%`);
	}
	const where = `WHERE ${parts.join(' AND ')}`;
	// One row per comment: aggregate the (alias-resolved, de-duplicated) indicators
	// it was matched to. total counts distinct comments to keep pagination correct.
	const total = sqlite
		.prepare(`SELECT COUNT(DISTINCT ci.comment_id) AS c FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${where}`)
		.get(...params) as { c: number };
	const rows = sqlite
		.prepare(
			`SELECT c.id, c.body, c.subreddit, ` +
				`GROUP_CONCAT(DISTINCT ${CANONICAL_SQL}) AS indicators, ` +
				`COUNT(DISTINCT ${CANONICAL_SQL}) AS n_indicators ` +
				`FROM comment_indicators ci JOIN comments c ON ci.comment_id = c.id ${CANONICAL_JOIN} ${where} ` +
				`GROUP BY c.id ORDER BY n_indicators DESC, c.id LIMIT ? OFFSET ?`
		)
		.all(...params, o.limit ?? 50, o.offset ?? 0) as {
		id: string;
		body: string;
		subreddit: string;
		indicators: string;
		n_indicators: number;
	}[];
	return { rows, total: total.c };
}

// ---- explore: pipeline status -------------------------------------------

// Mirror of get_opinion_comment_ids() in src/isthisai/extract.py. Keep in sync with
// OPINION_KEYWORDS / OPINION_BOT_AUTHORS there: these define which comments are
// "candidates" to name a visual tell (keyword + length + non-bot).
// Topical / authenticity words only — NOT visual-cue words (those made the filter
// circular). Keep in sync with OPINION_KEYWORDS in src/isthisai/extract.py.
const OPINION_KEYWORDS = ['AI', 'real', 'fake', 'generated', 'obvious', 'look'];
const OPINION_BOT_AUTHORS = [
	'automoderator', 'qualityvote2', 'realorai-bot', 'isthisai-modteam', 'realorai-modteam',
	'isthisai-bot', 'botdefense'
];

function countCandidateComments(): number {
	const kwClause = OPINION_KEYWORDS.map(() => 'body LIKE ?').join(' OR ');
	const botPlaceholders = OPINION_BOT_AUTHORS.map(() => '?').join(',');
	const sql =
		`SELECT COUNT(*) AS c FROM comments WHERE body IS NOT NULL ` +
		`AND LOWER(COALESCE(author, '')) NOT IN (${botPlaceholders}) ` +
		`AND body NOT LIKE '%I am a bot%' AND LENGTH(body) >= 20 AND (${kwClause})`;
	const params = [...OPINION_BOT_AUTHORS, ...OPINION_KEYWORDS.map((k) => `%${k}%`)];
	return (prep(sql).get(...params) as { c: number }).c;
}

// Comments eligible for SEMANTIC expansion: the same length + non-bot + non-deleted
// gate as candidates, but WITHOUT the keyword clause (semantic finds comments that
// describe a tell without the seed's words). Mirror of the gate in semantic_expand()
// in src/isthisai/embed.py — KEEP THE 20 + bot list IN SYNC. 0 on a body-stripped DB.
function countSemanticEligible(): number {
	const botPlaceholders = OPINION_BOT_AUTHORS.map(() => '?').join(',');
	const sql =
		`SELECT COUNT(*) AS c FROM comments WHERE body IS NOT NULL ` +
		`AND LOWER(COALESCE(author, '')) NOT IN (${botPlaceholders}) ` +
		`AND body NOT LIKE '%I am a bot%' AND LENGTH(body) >= 20`;
	return (prep(sql).get(...OPINION_BOT_AUTHORS) as { c: number }).c;
}

export function pipelineStatus() {
	const one = (sql: string) => (prep(sql).get() as { c: number }).c;
	const hasTable = (name: string) =>
		(
			prep("SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name = ?").get(name) as {
				c: number;
			}
		).c > 0;
	const totalComments = one('SELECT COUNT(*) AS c FROM comments');
	const analysedComments = one('SELECT COUNT(DISTINCT comment_id) AS c FROM comment_indicators');
	// "Candidate" comments: those that could plausibly name a visual tell — the same
	// filter the pipeline samples from. Mirror of get_opinion_comment_ids() in
	// src/isthisai/extract.py; KEEP THESE LISTS IN SYNC with OPINION_KEYWORDS /
	// OPINION_BOT_AUTHORS there. (On a body-stripped aggregate deploy DB this returns 0,
	// since body/author are nulled — fine for the static build, which runs against the
	// full local DB at build time.)
	const candidateComments = countCandidateComments();
	// Comments semantic expansion is allowed to match (length + non-bot gate, no keyword).
	const semanticEligible = countSemanticEligible();
	const taxonomy = one('SELECT COUNT(*) AS c FROM indicator_taxonomy');
	const embeddedIndicators = one('SELECT COUNT(*) AS c FROM indicator_embeddings');
	// The aggregate-only deploy DB drops comment_embeddings (the ~2.8 GB of BLOBs);
	// report 0 rather than throwing on the missing table.
	const embeddedComments = hasTable('comment_embeddings')
		? one('SELECT COUNT(*) AS c FROM comment_embeddings')
		: 0;
	const llm = one(
		"SELECT COUNT(*) AS c FROM comment_indicators WHERE batch_id NOT LIKE 'semantic%' AND batch_id NOT LIKE 'keyword%'"
	);
	const semantic = one("SELECT COUNT(*) AS c FROM comment_indicators WHERE batch_id LIKE 'semantic%'");
	const keyword = one("SELECT COUNT(*) AS c FROM comment_indicators WHERE batch_id LIKE 'keyword%'");
	// The comments the language model actually read, summed across ALL extraction runs
	// (each `extract sample` reads ~8k). Uses comments_processed (actual work — also
	// handles interrupted runs), not sample_size (merely requested). Slightly over-counts
	// the small overlap between independent random samples; the exact distinct-read isn't
	// stored. (Distinct from analysedComments, which counts comments with any cue post-expansion.)
	const llmSample = one('SELECT COALESCE(SUM(comments_processed), 0) AS c FROM extraction_runs');
	const aliases = one('SELECT COUNT(*) AS c FROM indicator_aliases');
	const runs = sqlite
		.prepare(
			'SELECT batch_id, model, started_at, completed_at, sample_size, comments_processed ' +
				'FROM extraction_runs ORDER BY started_at DESC LIMIT 10'
		)
		.all() as {
		batch_id: string;
		model: string;
		started_at: string | null;
		completed_at: string | null;
		sample_size: number | null;
		comments_processed: number | null;
	}[];
	const categoryDist = sqlite
		.prepare(
			"SELECT COALESCE(category, '(uncategorised)') AS category, COUNT(*) AS count " +
				'FROM comment_indicators GROUP BY category ORDER BY count DESC'
		)
		.all() as { category: string; count: number }[];
	return {
		totalComments,
		candidateComments,
		semanticEligible,
		opinionKeywords: OPINION_KEYWORDS,
		analysedComments,
		taxonomy,
		embeddedIndicators,
		embeddedComments,
		llm,
		llmSample,
		semantic,
		keyword,
		aliases,
		runs,
		categoryDist
	};
}

/**
 * Single source of truth for the headline figures shown on the narrative pages
 * (About `/`, How it works). BOTH pages spread this, so they can never diverge — e.g.
 * `top` is always the Noise-excluded #1 (same convention as the Explore Top Indicators
 * table/graphs), which is what fixed the earlier "It's AI" mismatch. When a new shared
 * figure is needed, add it HERE rather than computing it in a page load.
 */
export function headlineStats() {
	const s = pipelineStatus();
	return {
		totalComments: s.totalComments,
		candidates: s.candidateComments,
		eligible: s.semanticEligible,
		analysed: s.analysedComments,
		embedded: s.embeddedComments,
		llmSample: s.llmSample,
		semantic: s.semantic,
		top: topIndicators({ excludeNoise: true, limit: 1 })[0] ?? null
	};
}
