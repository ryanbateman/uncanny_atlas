import { sqlite, prep } from './db';

/**
 * Curate (write) operations + reads specific to the editing screens.
 *
 * Cascade scope is preserved exactly from the original Flask admin (admin.py):
 * category/confirm operations key on the raw `indicator` phrase and therefore
 * cascade to every comment row sharing that phrase. The new piece is real
 * canonicalization (merge/unmerge), which finally connects the long-orphaned
 * indicator_aliases table + comment_indicators.canonical_indicator column.
 */

export const CATEGORIES = [
	'Anatomy',
	'Physics',
	'Artifacts',
	'Style',
	'Text & Detail',
	'Motion',
	'Context',
	'Meta',
	'Noise'
] as const;

export type Mode = 'uncategorised' | 'noise' | 'both' | 'all' | 'seeds';

// `col` lets callers qualify the column (e.g. ci.category) when the query joins.
function modeFilter(mode: Mode, col = 'category'): string {
	if (mode === 'noise') return `${col} = 'Noise'`;
	if (mode === 'both') return `(${col} IS NULL OR ${col} = 'Noise')`;
	if (mode === 'all' || mode === 'seeds') return '1 = 1';
	return `${col} IS NULL`;
}

// ---- indicators screen (reads) -----------------------------------------

export function indicatorStats() {
	const one = (sql: string) => (prep(sql).get() as { c: number }).c;
	return {
		categorised: one("SELECT COUNT(*) AS c FROM comment_indicators WHERE category IS NOT NULL AND category != 'Noise'"),
		uncategorised: one('SELECT COUNT(*) AS c FROM comment_indicators WHERE category IS NULL'),
		noiseUnreviewed: one(
			"SELECT COUNT(*) AS c FROM comment_indicators WHERE category = 'Noise' AND (reviewed = 0 OR reviewed IS NULL)"
		),
		noiseReviewed: one("SELECT COUNT(*) AS c FROM comment_indicators WHERE category = 'Noise' AND reviewed = 1")
	};
}

/**
 * The auto-excluded stop-list (verdicts / tool names / bare subjects), persisted to
 * metadata by the extraction pipeline. These phrases are dropped at extraction and
 * never reach the categorize queue; existing rows are forced to Noise.
 */
export function stopIndicators(): { list: string[]; excludedPhrases: number } {
	const row = sqlite
		.prepare("SELECT value FROM _isthisai_metadata WHERE key = 'stop_indicators'")
		.get() as { value: string } | undefined;
	let list: string[] = [];
	try {
		list = row?.value ? (JSON.parse(row.value) as string[]) : [];
	} catch {
		list = [];
	}
	let excludedPhrases = 0;
	if (list.length) {
		const ph = list.map(() => '?').join(',');
		const r = sqlite
			.prepare(
				`SELECT COUNT(DISTINCT indicator) AS c FROM comment_indicators ` +
					`WHERE category = 'Noise' AND LOWER(indicator) IN (${ph})`
			)
			.get(...list.map((s) => s.toLowerCase())) as { c: number };
		excludedPhrases = r.c;
	}
	return { list, excludedPhrases };
}

type IndicatorRow = {
	indicator: string;
	cnt: number;
	current_category: string;
	reviewed: number;
	is_seed: number;
	// Merge state (Curate -> Merge). alias_of is the canonical this raw phrase is
	// folded into on the Explore side (null if it isn't merged); merged_count is how
	// many other phrases are folded INTO this one (i.e. this phrase is a canonical).
	alias_of: string | null;
	merged_count: number;
};

const SORTS: Record<string, string> = {
	freq_desc: 'ORDER BY cnt DESC',
	freq_asc: 'ORDER BY cnt ASC',
	len_desc: 'ORDER BY LENGTH(indicator) DESC',
	len_asc: 'ORDER BY LENGTH(indicator) ASC'
};

// One unified listing for the merged Indicators screen. Every mode except "seeds"
// lists the DATA (comment_indicators) with an is_seed flag (LEFT JOIN taxonomy);
// "seeds" lists the taxonomy directly, including seeds with no matches yet.
export function listIndicators(
	opts: { mode?: Mode; search?: string; sort?: string; limit?: number; offset?: number; showReviewed?: boolean } = {}
): IndicatorRow[] {
	const mode = opts.mode ?? 'uncategorised';
	const order = SORTS[opts.sort ?? 'freq_desc'] ?? SORTS.freq_desc;
	const limit = opts.limit ?? 50;
	const offset = opts.offset ?? 0;
	if (mode === 'seeds') {
		const params: unknown[] = [];
		let where = '';
		if (opts.search) {
			where = 'WHERE t.indicator_pattern LIKE ?';
			params.push(`%${opts.search}%`);
		}
		params.push(limit, offset);
		return sqlite
			.prepare(
				`SELECT t.indicator_pattern AS indicator, ` +
					`(SELECT COUNT(*) FROM comment_indicators ci WHERE ci.indicator = t.indicator_pattern) AS cnt, ` +
					`COALESCE(t.category, '') AS current_category, 0 AS reviewed, 1 AS is_seed, ` +
					`(SELECT canonical FROM indicator_aliases WHERE alias = t.indicator_pattern) AS alias_of, ` +
					`(SELECT COUNT(*) FROM indicator_aliases WHERE canonical = t.indicator_pattern) AS merged_count ` +
					`FROM indicator_taxonomy t ${where} ${order} LIMIT ? OFFSET ?`
			)
			.all(...params) as IndicatorRow[];
	}
	let filter = modeFilter(mode, 'ci.category');
	const params: unknown[] = [];
	if (opts.search) {
		filter = `(${filter}) AND ci.indicator LIKE ?`;
		params.push(`%${opts.search}%`);
	}
	if (!opts.showReviewed) filter = `(${filter}) AND (ci.reviewed = 0 OR ci.reviewed IS NULL)`;
	params.push(limit, offset);
	return sqlite
		.prepare(
			`SELECT ci.indicator AS indicator, COUNT(*) AS cnt, ` +
				`MAX(COALESCE(ci.category, '')) AS current_category, ` +
				`MAX(COALESCE(ci.reviewed, 0)) AS reviewed, ` +
				`MAX(CASE WHEN t.indicator_pattern IS NOT NULL THEN 1 ELSE 0 END) AS is_seed, ` +
				`(SELECT canonical FROM indicator_aliases WHERE alias = ci.indicator) AS alias_of, ` +
				`(SELECT COUNT(*) FROM indicator_aliases WHERE canonical = ci.indicator) AS merged_count ` +
				`FROM comment_indicators ci ` +
				`LEFT JOIN indicator_taxonomy t ON t.indicator_pattern = ci.indicator ` +
				`WHERE ${filter} GROUP BY ci.indicator ${order} LIMIT ? OFFSET ?`
		)
		.all(...params) as IndicatorRow[];
}

// Distinct indicators matching a search within a mode — for the "set all N" bulk action.
export function countIndicators(
	opts: { mode?: Mode; search?: string; showReviewed?: boolean } = {}
): number {
	const mode = opts.mode ?? 'uncategorised';
	if (mode === 'seeds') {
		const params: unknown[] = [];
		let where = '';
		if (opts.search) {
			where = 'WHERE indicator_pattern LIKE ?';
			params.push(`%${opts.search}%`);
		}
		return (sqlite.prepare(`SELECT COUNT(*) AS c FROM indicator_taxonomy ${where}`).get(...params) as { c: number }).c;
	}
	let filter = modeFilter(mode);
	const params: unknown[] = [];
	if (opts.search) {
		filter = `(${filter}) AND indicator LIKE ?`;
		params.push(`%${opts.search}%`);
	}
	if (!opts.showReviewed) filter = `(${filter}) AND (reviewed = 0 OR reviewed IS NULL)`;
	return (sqlite.prepare(`SELECT COUNT(DISTINCT indicator) AS c FROM comment_indicators WHERE ${filter}`).get(...params) as { c: number }).c;
}

// ---- indicators screen (writes) — cascade by phrase --------------------

// "Pending re-expansion": taxonomy patterns that have been (re)categorised to a
// real (non-Noise) category since the last semantic run. Each is a clue that
// expansion could now gather comments for — a nudge to re-run `embed semantic`.
// Stored as a JSON set in _isthisai_metadata; semantic_expand clears it.
const PENDING_KEY = 'pending_expansion';

function getPending(): string[] {
	const row = sqlite
		.prepare('SELECT value FROM _isthisai_metadata WHERE key = ?')
		.get(PENDING_KEY) as { value: string } | undefined;
	try {
		return row?.value ? (JSON.parse(row.value) as string[]) : [];
	} catch {
		return [];
	}
}

function updatePending(add: string[], remove: string[] = []) {
	const set = new Set(getPending());
	for (const p of remove) set.delete(p);
	for (const p of add) set.add(p);
	sqlite
		.prepare('INSERT OR REPLACE INTO _isthisai_metadata (key, value) VALUES (?, ?)')
		.run(PENDING_KEY, JSON.stringify([...set]));
}

/** Count (and list) of clues newly opened up for expansion since the last run. */
export function pendingExpansion(): { count: number; patterns: string[] } {
	const patterns = getPending();
	return { count: patterns.length, patterns };
}

/**
 * Set a category on an indicator and every comment that cites it. If the phrase is
 * part of a merge group, this cascades to the WHOLE group (the canonical + all its
 * aliases) — a merged indicator is one indicator, so it carries one category. Returns
 * the number of distinct phrases affected (1 unless the phrase is merged).
 */
export function assignCategory(indicator: string, category: string | null): number {
	const phrases = groupPhrases(terminalCanonical(indicator));
	const tx = sqlite.transaction(() => writeCategory(phrases, category));
	tx();
	return phrases.length;
}

export function confirmIndicator(indicator: string) {
	prep('UPDATE comment_indicators SET reviewed = 1 WHERE indicator = ?').run(indicator);
}

export function assignBySubstring(substring: string, category: string, mode: Mode): number {
	const filter = modeFilter(mode);
	const like = `%${substring}%`;
	// Phrases matching the search within the mode, plus any taxonomy patterns that match
	// (some seeds have no comments yet) — then expanded to their whole merge groups, so a
	// bulk edit can never split a merged indicator across categories.
	const matched = (
		sqlite
			.prepare(`SELECT DISTINCT indicator FROM comment_indicators WHERE ${filter} AND indicator LIKE ?`)
			.all(like) as { indicator: string }[]
	).map((r) => r.indicator);
	const matchedTax = (
		sqlite
			.prepare('SELECT indicator_pattern AS p FROM indicator_taxonomy WHERE indicator_pattern LIKE ?')
			.all(like) as { p: string }[]
	).map((r) => r.p);
	const phrases = expandToGroups([...matched, ...matchedTax]);
	let changed = 0;
	const tx = sqlite.transaction(() => {
		changed = writeCategory(phrases, category);
	});
	tx();
	return changed;
}

export function resetNoise(substring?: string): number {
	const info = substring
		? sqlite
				.prepare("UPDATE comment_indicators SET category = NULL WHERE category = 'Noise' AND indicator LIKE ?")
				.run(`%${substring}%`)
		: prep("UPDATE comment_indicators SET category = NULL WHERE category = 'Noise'").run();
	return info.changes;
}

// ---- taxonomy screen ----------------------------------------------------

export function taxonomyTotal(): number {
	return (prep('SELECT COUNT(*) AS c FROM indicator_taxonomy').get() as { c: number }).c;
}

export function listTaxonomy(opts: { search?: string; category?: string; sort?: string; limit?: number; offset?: number } = {}) {
	const parts: string[] = [];
	const params: unknown[] = [];
	if (opts.search) {
		parts.push('t.indicator_pattern LIKE ?');
		params.push(`%${opts.search}%`);
	}
	if (opts.category) {
		parts.push('t.category = ?');
		params.push(opts.category);
	}
	const where = parts.length ? `WHERE ${parts.join(' AND ')}` : '';
	const order =
		{
			usage_desc: 'ORDER BY usage DESC',
			usage_asc: 'ORDER BY usage ASC',
			alpha_asc: 'ORDER BY t.indicator_pattern ASC',
			alpha_desc: 'ORDER BY t.indicator_pattern DESC'
		}[opts.sort ?? 'usage_desc'] ?? 'ORDER BY usage DESC';
	return sqlite
		.prepare(
			`SELECT t.indicator_pattern, t.category, t.subcategory, COUNT(ci.indicator) AS usage ` +
				`FROM indicator_taxonomy t LEFT JOIN comment_indicators ci ON ci.indicator = t.indicator_pattern ` +
				`${where} GROUP BY t.indicator_pattern ${order} LIMIT ? OFFSET ?`
		)
		.all(...params, opts.limit ?? 50, opts.offset ?? 0) as {
		indicator_pattern: string;
		category: string;
		subcategory: string | null;
		usage: number;
	}[];
}

/** Taxonomy category change cascades to comment_indicators (matches admin.py). */
export function updateTaxonomy(pattern: string, category: string, subcategory: string | null) {
	const tx = sqlite.transaction(() => {
		sqlite
			.prepare('UPDATE indicator_taxonomy SET category = ?, subcategory = ? WHERE indicator_pattern = ?')
			.run(category, subcategory, pattern);
		prep('UPDATE comment_indicators SET category = ? WHERE indicator = ?').run(category, pattern);
	});
	tx();
}

export function addTaxonomy(pattern: string, category: string, subcategory: string | null): boolean {
	const info = sqlite
		.prepare('INSERT OR IGNORE INTO indicator_taxonomy (indicator_pattern, category, subcategory) VALUES (?, ?, ?)')
		.run(pattern, category, subcategory);
	return info.changes > 0;
}

export function deleteTaxonomy(pattern: string) {
	const tx = sqlite.transaction(() => {
		prep('DELETE FROM indicator_taxonomy WHERE indicator_pattern = ?').run(pattern);
		prep('DELETE FROM indicator_embeddings WHERE indicator_pattern = ?').run(pattern);
	});
	tx();
}

// ---- merge / canonicalization ------------------------------------------

/** Existing merges: canonical -> member alias phrases, with combined usage + category. */
export function listMerges() {
	const aliases = sqlite
		.prepare('SELECT alias, canonical FROM indicator_aliases ORDER BY canonical, alias')
		.all() as { alias: string; canonical: string }[];
	const byCanonical = new Map<string, string[]>();
	for (const { alias, canonical } of aliases) {
		const arr = byCanonical.get(canonical) ?? [];
		arr.push(alias);
		byCanonical.set(canonical, arr);
	}
	const usageStmt = prep('SELECT COUNT(*) AS c FROM comment_indicators WHERE indicator = ?');
	return [...byCanonical.entries()]
		.map(([canonical, members]) => {
			const phrases = [canonical, ...members];
			const usage = phrases.reduce((sum, p) => sum + (usageStmt.get(p) as { c: number }).c, 0);
			// The group's real category (Noise excluded — it's an orthogonal flag), so the
			// builder can show/inherit it when adding members to this group.
			const ph = phrases.map(() => '?').join(',');
			const cat = sqlite
				.prepare(
					`SELECT category FROM comment_indicators WHERE indicator IN (${ph}) ` +
						`AND category IS NOT NULL AND category <> 'Noise' ` +
						`GROUP BY category ORDER BY COUNT(*) DESC, category ASC LIMIT 1`
				)
				.get(...phrases) as { category: string } | undefined;
			return { canonical, members, usage, category: cat?.category ?? null };
		})
		.sort((a, b) => b.usage - a.usage);
}

/**
 * Candidate phrases for the manual merge builder: distinct indicator phrases matching
 * `query`, EXCLUDING phrases already folded into a canonical (they already belong to a
 * group), plus matching taxonomy patterns that have no comments yet. Usage desc.
 */
export function searchMergeCandidates(
	query: string,
	limit = 30
): { phrase: string; usage: number; is_seed: number }[] {
	if (!query.trim()) return [];
	const aliased = new Set(
		(prep('SELECT alias FROM indicator_aliases').all() as { alias: string }[]).map((r) => r.alias)
	);
	const like = `%${query}%`;
	const rows = sqlite
		.prepare(
			`SELECT ci.indicator AS phrase, COUNT(*) AS usage, ` +
				`MAX(CASE WHEN t.indicator_pattern IS NOT NULL THEN 1 ELSE 0 END) AS is_seed ` +
				`FROM comment_indicators ci ` +
				`LEFT JOIN indicator_taxonomy t ON t.indicator_pattern = ci.indicator ` +
				`WHERE ci.indicator LIKE ? GROUP BY ci.indicator`
		)
		.all(like) as { phrase: string; usage: number; is_seed: number }[];
	const have = new Set(rows.map((r) => r.phrase));
	const seedOnly = (
		sqlite
			.prepare('SELECT indicator_pattern AS phrase FROM indicator_taxonomy WHERE indicator_pattern LIKE ?')
			.all(like) as { phrase: string }[]
	).map((r) => r.phrase);
	for (const phrase of seedOnly) if (!have.has(phrase)) rows.push({ phrase, usage: 0, is_seed: 1 });
	return rows
		.filter((r) => !aliased.has(r.phrase))
		.sort((a, b) => b.usage - a.usage || a.phrase.localeCompare(b.phrase))
		.slice(0, limit);
}

/**
 * Impact preview for a prospective merge: the combined DISTINCT-comment count across the
 * phrase set (what the merged indicator's Explore "Comments" figure becomes — same
 * semantics as topIndicators), plus each phrase's own distinct-comment count.
 */
export function mergeImpact(phrases: string[]): {
	comments: number;
	perPhrase: { phrase: string; comments: number }[];
} {
	if (!phrases.length) return { comments: 0, perPhrase: [] };
	const ph = phrases.map(() => '?').join(',');
	const comments = (
		sqlite
			.prepare(`SELECT COUNT(DISTINCT comment_id) AS c FROM comment_indicators WHERE indicator IN (${ph})`)
			.get(...phrases) as { c: number }
	).c;
	const per = prep('SELECT COUNT(DISTINCT comment_id) AS c FROM comment_indicators WHERE indicator = ?');
	const perPhrase = phrases.map((phrase) => ({
		phrase,
		comments: (per.get(phrase) as { c: number }).c
	}));
	return { comments, perPhrase };
}

/**
 * Follow the alias chain to its terminal canonical. The alias graph is
 * functional (one canonical per alias), so this also guards against cycles.
 */
function terminalCanonical(phrase: string): string {
	const stmt = prep('SELECT canonical FROM indicator_aliases WHERE alias = ?');
	const seen = new Set<string>();
	let cur = phrase;
	for (;;) {
		if (seen.has(cur)) break; // defensive against a pre-existing cycle
		seen.add(cur);
		const row = stmt.get(cur) as { canonical: string } | undefined;
		if (!row || row.canonical === cur) break;
		cur = row.canonical;
	}
	return cur;
}

/** Every phrase that resolves to this canonical: the canonical itself + its aliases. */
function groupPhrases(canonical: string): string[] {
	const aliases = (
		prep('SELECT alias FROM indicator_aliases WHERE canonical = ?').all(canonical) as { alias: string }[]
	).map((r) => r.alias);
	return [canonical, ...aliases];
}

/**
 * Write a category to a set of phrases — their comment rows (marked reviewed), their
 * taxonomy patterns (the source of truth for re-expansion), and the pending set. No
 * transaction of its own; call inside one. Returns the number of comment rows changed.
 */
function writeCategory(phrases: string[], category: string | null): number {
	if (!phrases.length) return 0;
	const ph = phrases.map(() => '?').join(',');
	const info = sqlite
		.prepare(`UPDATE comment_indicators SET category = ?, reviewed = 1 WHERE indicator IN (${ph})`)
		.run(category, ...phrases);
	if (category === 'Noise') {
		// Noise and Seed are mutually exclusive: a non-indicator must not be a seed.
		// Drop any seed (taxonomy) + its embedding — otherwise the embedding would still
		// be expanded from (embed semantic seeds off indicator_embeddings; an orphaned
		// embedding with no taxonomy row is NOT skipped). Remove from pending too.
		sqlite.prepare(`DELETE FROM indicator_taxonomy WHERE indicator_pattern IN (${ph})`).run(...phrases);
		sqlite.prepare(`DELETE FROM indicator_embeddings WHERE indicator_pattern IN (${ph})`).run(...phrases);
		updatePending([], phrases);
	} else if (category) {
		sqlite
			.prepare(`UPDATE indicator_taxonomy SET category = ? WHERE indicator_pattern IN (${ph})`)
			.run(category, ...phrases);
		const pats = (
			sqlite
				.prepare(`SELECT indicator_pattern AS p FROM indicator_taxonomy WHERE indicator_pattern IN (${ph})`)
				.all(...phrases) as { p: string }[]
		).map((r) => r.p);
		// Real category → expansion could now gather comments for it (pending).
		if (pats.length) updatePending(pats);
	}
	return info.changes;
}

/** Expand a set of phrases to the full merge groups they belong to (deduplicated). */
function expandToGroups(phrases: string[]): string[] {
	const out = new Set<string>();
	for (const p of phrases) for (const g of groupPhrases(terminalCanonical(p))) out.add(g);
	return [...out];
}

/**
 * Merge alias phrases into a canonical. Writes indicator_aliases AND backfills
 * comment_indicators.canonical_indicator so analytical queries collapse them.
 *
 * Chain/cycle-safe: the chosen canonical is first resolved to its terminal (so
 * picking a name that is itself an alias folds into the real canonical), and if
 * any merged phrase is itself a canonical, its whole sub-group is absorbed.
 *
 * A merge is one indicator, so it carries one category: the caller (the Merge form)
 * must pass an explicit category (or 'Noise'), which is written to the whole group.
 * There is no inference — the choice is always deliberate and visible.
 */
export function merge(canonical: string, aliases: string[], category: string) {
	const tx = sqlite.transaction(() => {
		const target = terminalCanonical(canonical);
		const insert = prep('INSERT OR REPLACE INTO indicator_aliases (alias, canonical) VALUES (?, ?)');
		const absorb = prep('UPDATE indicator_aliases SET canonical = ? WHERE canonical = ?');
		const backfill = prep(
			'UPDATE comment_indicators SET canonical_indicator = ? WHERE indicator = ? OR canonical_indicator = ?'
		);
		for (const alias of aliases) {
			if (alias === target) continue; // no self-alias
			absorb.run(target, alias); // re-point any sub-group this phrase was canonical for
			insert.run(alias, target);
			backfill.run(target, alias, alias);
		}
		// Ensure the canonical's own rows carry the marker; drop any self-alias.
		prep('UPDATE comment_indicators SET canonical_indicator = ? WHERE indicator = ?').run(target, target);
		prep('DELETE FROM indicator_aliases WHERE alias = canonical').run();
		// Apply the chosen category to every member, so the merged indicator is
		// categorised consistently everywhere.
		writeCategory(groupPhrases(target), category);
	});
	tx();
}

/** Reverse a merge: drop aliases for this canonical and clear their markers. */
export function unmerge(canonical: string) {
	const tx = sqlite.transaction(() => {
		prep('UPDATE comment_indicators SET canonical_indicator = NULL WHERE canonical_indicator = ?').run(canonical);
		prep('DELETE FROM indicator_aliases WHERE canonical = ?').run(canonical);
	});
	tx();
}

/**
 * Rename a canonical indicator everywhere it resolves. The old name (and all its
 * aliases) become aliases of the new name, so every comment that resolved to the
 * old canonical now resolves to the new one. Renaming to a name that already
 * exists effectively merges into it.
 */
export function renameCanonical(oldName: string, newName: string) {
	const o = oldName.trim();
	const nn = newName.trim();
	if (!o || !nn || o === nn) return;
	const tx = sqlite.transaction(() => {
		// Re-point every alias of the old canonical to the new name.
		prep('UPDATE indicator_aliases SET canonical = ? WHERE canonical = ?').run(nn, o);
		// The old name itself becomes an alias of the new name.
		prep('INSERT OR REPLACE INTO indicator_aliases (alias, canonical) VALUES (?, ?)').run(o, nn);
		// If the new name was itself aliased away, drop that so it's a true canonical.
		prep('DELETE FROM indicator_aliases WHERE alias = ?').run(nn);
		// Re-point the materialised column for both the old canonical and its raw rows.
		sqlite
			.prepare('UPDATE comment_indicators SET canonical_indicator = ? WHERE canonical_indicator = ? OR indicator = ?')
			.run(nn, o, o);
		prep('DELETE FROM indicator_aliases WHERE alias = canonical').run();
	});
	tx();
}

/**
 * Remove a single comment's association with a canonical indicator — deletes the
 * comment_indicators row(s) for that comment that resolve to the canonical. Use
 * for obviously-wrong attributions; the comment itself is untouched.
 */
export function removeAssociation(commentId: string, canonical: string): number {
	const info = sqlite
		.prepare(
			`DELETE FROM comment_indicators WHERE comment_id = ? AND ` +
				`COALESCE((SELECT canonical FROM indicator_aliases WHERE alias = comment_indicators.indicator), ` +
				`canonical_indicator, indicator) = ?`
		)
		.run(commentId, canonical);
	return info.changes;
}

// ---- embedding-based cluster suggestions --------------------------------

function bufToFloat32(buf: Buffer): Float32Array {
	return new Float32Array(buf.buffer, buf.byteOffset, Math.floor(buf.byteLength / 4));
}

function normalize(v: Float32Array): Float32Array {
	let norm = 0;
	for (let i = 0; i < v.length; i++) norm += v[i] * v[i];
	norm = Math.sqrt(norm) || 1;
	const out = new Float32Array(v.length);
	for (let i = 0; i < v.length; i++) out[i] = v[i] / norm;
	return out;
}

function dot(a: Float32Array, b: Float32Array): number {
	let s = 0;
	const n = Math.min(a.length, b.length);
	for (let i = 0; i < n; i++) s += a[i] * b[i];
	return s;
}

/**
 * Greedy cosine clustering of taxonomy patterns, mirroring the old admin
 * /clusters logic. Returns only multi-member clusters above the threshold,
 * each annotated with per-phrase usage counts, ordered by total usage.
 */
export function clusterSuggestions(threshold = 0.7) {
	// Phrases already folded into a canonical (present as an alias) are done —
	// drop them from the pool so a just-merged cluster doesn't keep re-suggesting
	// itself (which reads as "the merge didn't save").
	const aliased = new Set(
		(prep('SELECT alias FROM indicator_aliases').all() as { alias: string }[]).map(
			(r) => r.alias
		)
	);
	const rows = (
		sqlite
			.prepare('SELECT indicator_pattern, embedding FROM indicator_embeddings')
			.all() as { indicator_pattern: string; embedding: Buffer }[]
	).filter((r) => !aliased.has(r.indicator_pattern));
	const patterns = rows.map((r) => r.indicator_pattern);
	const vecs = rows.map((r) => normalize(bufToFloat32(r.embedding)));

	const usageStmt = prep('SELECT COUNT(*) AS c FROM comment_indicators WHERE indicator = ?');
	const usageOf = (p: string) => (usageStmt.get(p) as { c: number }).c;

	const assigned = new Set<number>();
	const clusters: { members: { phrase: string; usage: number }[]; total: number }[] = [];
	for (let i = 0; i < patterns.length; i++) {
		if (assigned.has(i)) continue;
		const group = [i];
		assigned.add(i);
		for (let j = i + 1; j < patterns.length; j++) {
			if (assigned.has(j)) continue;
			if (dot(vecs[i], vecs[j]) >= threshold) {
				group.push(j);
				assigned.add(j);
			}
		}
		if (group.length < 2) continue;
		const members = group
			.map((idx) => ({ phrase: patterns[idx], usage: usageOf(patterns[idx]) }))
			.sort((a, b) => b.usage - a.usage);
		clusters.push({ members, total: members.reduce((s, m) => s + m.usage, 0) });
	}
	return clusters.sort((a, b) => b.total - a.total);
}
