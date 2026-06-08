<script lang="ts">
	import { enhance } from '$app/forms';
	import Hint from '$lib/Hint.svelte';
	import { n } from '$lib/format';
	let { data, form } = $props();

	// Pagination links preserve the current filters and set the offset.
	const pageUrl = (offset: number) => {
		const p = new URLSearchParams();
		if (data.search) p.set('search', data.search);
		p.set('mode', data.mode);
		p.set('sort', data.sort);
		p.set('limit', String(data.limit));
		if (!data.showReviewed) p.set('reviewed', 'hide');
		if (offset > 0) p.set('offset', String(offset));
		return `?${p}`;
	};
</script>

<h2>Categorise indicators</h2>
<p class="page-desc">
	Triage extracted indicators and manage expansion seeds in one place. Setting a category
	<strong>cascades to every comment</strong> that cites the phrase; mark non-indicators as
	<code>Noise</code>. Each row is a <strong>raw extracted phrase</strong>: merged duplicates
	(Curate → Merge) are still listed separately here — flagged in the <strong>Merge group</strong>
	column — and only collapse into a single entry on the Explore side. Categorising a merged phrase
	<strong>cascades to its whole group</strong>, so the indicator keeps one category everywhere.
</p>
<p class="page-desc">
	<strong>Seeds</strong> are the phrases semantic expansion hunts for, and they're set automatically
	during the pipeline: the <em>build taxonomy</em> step promotes the ~200 most-frequent extracted
	phrases to seeds and leaves the long tail of one-off phrases un-seeded. So most rows here are
	observations the model saw once, not active seeds. Toggle <strong>Seed</strong> to add or remove one
	by hand; a newly-seeded phrase needs an <code>embed indicators</code> + <code>embed semantic</code>
	run before it gathers comments.
</p>

{#if form?.message}<div class="flash success">{form.message}</div>{/if}

{#if data.pending.count > 0}
	<div class="flash nudge">
		<strong>{n(data.pending.count)}</strong> indicator{data.pending.count === 1 ? '' : 's'}
		opened up since the last expansion. Run <code>uv run isthisai-embed semantic</code> to gather
		their comments (your Noise decisions are respected, and re-running is safe).
	</div>
{/if}

<div class="cards">
	<div class="card"><div class="value">{n(data.stats.categorised)}</div><div class="label">Categorised <Hint text="Indicator rows assigned to a real category (anything except Noise)." /></div></div>
	<div class="card"><div class="value">{n(data.stats.uncategorised)}</div><div class="label">Uncategorised <Hint text="Indicator rows with no category yet." /></div></div>
	<div class="card"><div class="value">{n(data.stats.noiseUnreviewed + data.stats.noiseReviewed)}</div><div class="label">Noise <Hint text="Rows marked Noise — excluded from every chart and ranking." /></div></div>
	<div class="card"><div class="value">{n(data.seedsTotal)}</div><div class="label">Seeds <Hint text="Indicators in the taxonomy that semantic expansion hunts for. Browse them with Mode → Seeds." /></div></div>
</div>

<details class="panel stop-list">
	<summary>
		<strong>{data.stopList.list.length}</strong> phrases auto-excluded by the stop-list — {data.stopList.excludedPhrases}
		present in your data, forced to <code>Noise</code>
		<Hint text="Post/source platforms and pure verdicts are dropped at extraction and forced to Noise — they're never visual indicators. They don't appear in the Uncategorised queue. Defined in STOP_INDICATORS (extract.py)." />
	</summary>
	<div class="pill-list" style="margin-top:10px">
		{#each data.stopList.list as s (s)}<span class="pill">{s}</span>{/each}
	</div>
</details>

<div class="table-card">
<form class="filter-bar table-controls" method="get">
	<label>
		<span>Search <Hint text="Find any indicator — including already-categorised ones (which the mode filters don't surface). Press Enter, then either edit rows or use the bulk bar below." /></span>
		<input type="search" name="search" value={data.search} placeholder="phrase… (Enter)" />
	</label>
	<label>
		Mode
		<select name="mode" onchange={(e) => e.currentTarget.form?.requestSubmit()}>
			<option value="uncategorised" selected={data.mode === 'uncategorised'}>Uncategorised</option>
			<option value="noise" selected={data.mode === 'noise'}>Noise</option>
			<option value="both" selected={data.mode === 'both'}>Both</option>
			<option value="all" selected={data.mode === 'all'}>All</option>
			<option value="seeds" selected={data.mode === 'seeds'}>Seeds</option>
		</select>
	</label>
	<label>
		Sort
		<select name="sort" onchange={(e) => e.currentTarget.form?.requestSubmit()}>
			<option value="freq_desc" selected={data.sort === 'freq_desc'}>Frequency ↓</option>
			<option value="freq_asc" selected={data.sort === 'freq_asc'}>Frequency ↑</option>
			<option value="len_desc" selected={data.sort === 'len_desc'}>Length ↓</option>
			<option value="len_asc" selected={data.sort === 'len_asc'}>Length ↑</option>
		</select>
	</label>
	<label>
		Limit
		<select name="limit" onchange={(e) => e.currentTarget.form?.requestSubmit()}>
			{#each [25, 50, 100, 200] as l (l)}
				<option value={l} selected={data.limit === l}>{l}</option>
			{/each}
		</select>
	</label>
	{#if data.mode !== 'seeds'}
		<label>
			Reviewed
			<select name="reviewed" onchange={(e) => e.currentTarget.form?.requestSubmit()}>
				<option value="hide" selected={!data.showReviewed}>Hide reviewed</option>
				<option value="show" selected={data.showReviewed}>Show reviewed</option>
			</select>
		</label>
	{/if}
</form>

{#if data.search && data.total > 0}
	<div class="bulk-bar">
		<form method="post" action="?/batch" use:enhance class="filter-bar" style="margin:0; align-items:end">
			<span class="bulk-label">Set all <strong>{n(data.total)}</strong> matching “{data.search}” →</span>
			<label>
				Category
				<select name="category" required>
					{#each data.categories as c (c)}<option value={c}>{c}</option>{/each}
				</select>
			</label>
			<input type="hidden" name="substring" value={data.search} />
			<input type="hidden" name="mode" value={data.mode} />
			<button type="submit">Apply to all</button>
		</form>
	</div>
{/if}

{#if data.rows.length}
<div class="table-scroll">
	<table>
		<thead>
			<tr>
				<th>Indicator</th>
					<th>Merge group <Hint text="Whether this phrase is part of a merge (set on Curate → Merge). “→ name” = it's folded into that canonical on the Explore side, counted as one indicator in Top indicators, Inspect, and Matches. “N merged” = N other phrases fold into this one. A dash means it's standalone." /></th>
				<th class="num">Comments <Hint text="How many comments cite this exact phrase. Assigning a category cascades to all of them." /></th>
				<th>Category <Hint text="Pick a category (or Noise) and Apply — it sets every comment with this phrase and marks it reviewed." /></th>
				<th>Seed <Hint text="Whether semantic expansion hunts for this indicator. Toggle on to make it a seed (then run embed indicators + semantic); off removes it as a seed (existing matches stay)." /></th>
			</tr>
		</thead>
		<tbody>
			{#each data.rows as row (row.indicator)}
				<tr>
					<td><a href="/explore/lookup?indicator={encodeURIComponent(row.alias_of || row.indicator)}" title="Inspect every comment that cites this indicator{row.alias_of ? ` (as “${row.alias_of}”)` : ''}">{row.indicator}</a></td>
						<td>
							{#if row.alias_of}
								<span class="merge-badge" title="Folded into “{row.alias_of}” on Explore — counted as that canonical in Top indicators, Inspect, and Matches. Still curated as its own phrase here.">→ {row.alias_of}</span>
							{:else if row.merged_count}
								<span class="merge-badge canon" title="{row.merged_count} other phrase(s) fold into this canonical on Explore.">{row.merged_count} merged</span>
							{:else}
								<span class="merge-none" title="Standalone — not part of any merge.">—</span>
							{/if}
						</td>
					<td class="num">{n(row.cnt)}</td>
					<td>
						<form method="post" action="?/assign" use:enhance style="display:flex;gap:6px;align-items:center">
							<input type="hidden" name="indicator" value={row.indicator} />
							<select name="category">
								<option value="" disabled selected={!row.current_category}>(none)</option>
								{#each data.categories as c (c)}
									<option value={c} selected={c === row.current_category}>{c}</option>
								{/each}
							</select>
							<button class="ghost" title="Apply this category to all comments with this phrase">Apply</button>
						</form>
					</td>
					<td>
						<form
							method="post"
							action="?/toggleSeed"
							use:enhance
							onsubmit={(e) => {
								if (row.is_seed && !confirm(`Remove “${row.indicator}” as an expansion seed?`)) e.preventDefault();
							}}
						>
							<input type="hidden" name="indicator" value={row.indicator} />
							<input type="hidden" name="on" value={row.is_seed ? 'false' : 'true'} />
							<input type="hidden" name="category" value={row.current_category} />
							<button class="ghost seed" class:on={row.is_seed} disabled={row.current_category === 'Noise' && !row.is_seed} title={row.current_category === 'Noise' && !row.is_seed ? 'Noise indicators are never expanded — clear the Noise category to seed this.' : row.is_seed ? 'Remove as expansion seed' : 'Make an expansion seed'}>
								{row.is_seed ? '● seed' : '○ seed'}
							</button>
						</form>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{:else}
<div class="table-empty">No indicators match these filters. Try a different Mode{#if data.search}, or clear the search{/if}.</div>
{/if}
{#if data.total > data.limit}
<div class="table-foot">
	<span>{data.offset + 1}–{Math.min(data.offset + data.limit, data.total)} of {n(data.total)}</span>
	<span class="pager">
		{#if data.offset > 0}<a href={pageUrl(data.offset - data.limit)}>← Prev</a>{/if}
		{#if data.offset + data.limit < data.total}<a href={pageUrl(data.offset + data.limit)}>Next →</a>{/if}
	</span>
</div>
{/if}
</div>

<h3>Add a new indicator <Hint text="Create a brand-new expansion seed — an indicator the model never extracted. After adding, run embed indicators + semantic for it to gather comments." /></h3>
<div class="panel">
	<form method="post" action="?/addSeed" use:enhance class="filter-bar" style="margin:0">
		<label>Indicator<input type="text" name="pattern" required placeholder="e.g. extra fingers" /></label>
		<label>
			Category
			<select name="category" required>
				{#each data.categories.filter((c) => c !== 'Noise') as c (c)}<option value={c}>{c}</option>{/each}
			</select>
		</label>
		<button type="submit">Add seed</button>
	</form>
</div>

<h3>Reset Noise <Hint text="Send Noise-tagged phrases back to uncategorised so they can be re-judged. Blank = all Noise, or narrow with a substring." /></h3>
<div class="panel">
	<form method="post" action="?/reset" use:enhance class="filter-bar" style="margin:0">
		<label>Substring (optional)<input type="text" name="substring" placeholder="blank = all Noise" /></label>
		<button type="submit" class="danger">Reset to uncategorised</button>
	</form>
</div>

<style>
	/* Bulk-assign bar: sits between the filters and the table inside the card. */
	.bulk-bar {
		margin-bottom: var(--space-3);
	}
	.bulk-label {
		align-self: center;
		font-size: var(--text-sm);
	}
	.seed {
		font-size: var(--text-xs);
		color: var(--muted);
		white-space: nowrap;
	}
	.seed.on {
		color: var(--accent);
		border-color: var(--accent);
	}
	/* .merge-badge / .merge-badge.canon / .merge-none are global (app.css) — shared with Explore. */
</style>
