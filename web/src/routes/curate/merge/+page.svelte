<script lang="ts">
	import { enhance } from '$app/forms';
	import type { SubmitFunction } from '@sveltejs/kit';
	import { untrack } from 'svelte';
	import Hint from '$lib/Hint.svelte';
	import { n } from '$lib/format';
	let { data, form } = $props();

	// ── Build a merge (client-side for snappy interaction; a light endpoint does the
	// candidate search + the combined-comment impact, so the expensive cluster
	// suggestion only runs on the page load, never per keystroke). ──
	type Cand = { phrase: string; usage: number; is_seed: number };
	// One-time builder seed from URL prefill links (Open in builder / + add).
	const seedSel: string[] = untrack(() => data.prefillSel ?? []);
	const seedInto: string | null = untrack(() => data.prefillInto);
	let q = $state('');
	let candidates = $state<Cand[]>([]);
	let searching = $state(false);
	let basket = $state<string[]>(seedSel);
	let mode = $state<'new' | 'existing'>(seedInto ? 'existing' : 'new');
	let newName = $state('');
	let category = $state(''); // used by "new", or "existing" when the group has no category yet
	let groupCanonical = $state(seedInto ?? '');

	let impact = $state(0);

	const group = $derived(
		mode === 'existing' && groupCanonical
			? (data.merges.find((m) => m.canonical === groupCanonical) ?? null)
			: null
	);
	const groupCategory = $derived(group?.category ?? null);
	const effectiveCategory = $derived(mode === 'existing' && groupCategory ? groupCategory : category);
	const targetCanonical = $derived(mode === 'new' ? newName.trim() : groupCanonical);
	const canMerge = $derived(basket.length > 0 && targetCanonical !== '' && effectiveCategory !== '');

	// Phrases whose combined DISTINCT-comment count the preview shows.
	const impactPhrases = $derived(
		group ? [...new Set([...basket, group.canonical, ...group.members])] : basket
	);

	function impactParams() {
		const p = new URLSearchParams();
		for (const ph of impactPhrases) p.append('p', ph);
		return p;
	}
	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	function search() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(runSearch, 160);
	}
	async function runSearch() {
		searching = true;
		const p = impactParams();
		if (q.trim()) p.set('q', q.trim());
		try {
			const r = await fetch(`/curate/merge/search?${p}`);
			const d = await r.json();
			candidates = (d.candidates as Cand[]).filter((c) => !basket.includes(c.phrase));
			impact = d.impact as number;
		} finally {
			searching = false;
		}
	}
	let impactTimer: ReturnType<typeof setTimeout> | undefined;
	async function runImpact() {
		const r = await fetch(`/curate/merge/search?${impactParams()}`);
		impact = ((await r.json()).impact as number) ?? 0;
	}
	function add(ph: string) {
		if (!basket.includes(ph)) basket = [...basket, ph];
		candidates = candidates.filter((c) => c.phrase !== ph);
	}
	function remove(ph: string) {
		basket = basket.filter((b) => b !== ph);
	}
	// Recompute just the combined-comment impact when the basket / target group changes
	// (a cheap COUNT — no candidate LIKE scan).
	$effect(() => {
		void impactPhrases;
		clearTimeout(impactTimer);
		impactTimer = setTimeout(runImpact, 120);
	});

	// Clear the builder after a successful merge (the phrases are now aliased). update()
	// refreshes the active-merges table + flash; then we reset the client-side state.
	const onMerged: SubmitFunction = () => async ({ result, update }) => {
		await update();
		if (result.type === 'success') {
			basket = [];
			newName = '';
			category = '';
			mode = 'new';
			groupCanonical = '';
			q = '';
			candidates = [];
			impact = 0;
		}
	};

	// Prefill links into the builder (full reload so the component re-seeds from the URL).
	const clusterLink = (members: string[]) => {
		const p = new URLSearchParams();
		for (const m of members) p.append('sel', m);
		p.set('threshold', String(data.threshold));
		return `?${p}#builder`;
	};
	const intoLink = (canonical: string) =>
		`?into=${encodeURIComponent(canonical)}&threshold=${data.threshold}#builder`;
</script>

<h2>Merge / canonical indicators</h2>
<p class="page-desc">
	Collapse scattered near-duplicate phrases (e.g. “six fingers”, “extra fingers”, “too many
	fingers”) into one canonical indicator. Merging writes an alias and rewrites
	<code>canonical_indicator</code>, so every analysis on the Explore side groups them together.
	Build a merge by hand below, or fold a suggested embedding cluster.
</p>
<p class="page-desc">
	<strong>Where this shows up:</strong> a merge collapses only the <em>phrase-level</em> Explore
	surfaces — <em>Top indicators</em>, <em>Inspect indicator</em>, and <em>Semantic matches</em> — into
	the canonical, combining their distinct-comment counts. The category charts (Mentions by category /
	over time / by subreddit) count by category, not phrase, so they are unchanged. And
	<em>Categorise / seeds</em> still lists each raw phrase individually (flagged with a merge badge),
	because curation works at the raw-phrase level. Because the members become one indicator, merging
	<strong>requires you to choose the group's category</strong> (or Noise) up front; it is applied to
	every member, and categorising any member afterwards re-applies to the whole group — so a merged
	indicator always carries one explicit category, never an inferred one.
</p>

{#if form?.message}<div class="flash success">{form.message}</div>{/if}

<datalist id="existing-canonicals">
	{#each data.canonicals as cn (cn)}<option value={cn}></option>{/each}
</datalist>

<!-- ── Build a merge (manual) ─────────────────────────────────────────── -->
<h3 id="builder">Build a merge <Hint text="Search for indicator phrases, add the ones that mean the same thing, choose whether they form a new canonical or join an existing group, then Merge." /></h3>
<div class="panel builder">
	<label class="b-search">
		<span>Add phrases <Hint text="Search indicator phrases not already in a merge; click a result to drop it in the basket." /></span>
		<input type="search" bind:value={q} oninput={search} placeholder="search phrases…" autocomplete="off" />
	</label>
	{#if q.trim()}
		<div class="cand-list">
			{#each candidates as c (c.phrase)}
				<button type="button" class="cand" onclick={() => add(c.phrase)}>
					<span class="cand-add">+ {c.phrase}</span>
					<span class="pill">{n(c.usage)}</span>
					{#if c.is_seed}<span class="seed-dot" title="Expansion seed">●</span>{/if}
				</button>
			{:else}
				<div class="muted pad">{searching ? 'Searching…' : `No unmerged phrases match “${q}”.`}</div>
			{/each}
		</div>
	{/if}

	<div class="basket">
		<div class="basket-head">Basket ({basket.length})</div>
		{#if basket.length}
			<div class="basket-items">
				{#each basket as b (b)}
					<span class="bchip">{b} <button type="button" class="bchip-x" title="Remove" onclick={() => remove(b)}>✕</button></span>
				{/each}
			</div>
			<div class="preview">→ <strong>{n(impact)}</strong> comments combined{#if group} (incl. “{group.canonical}”){/if}</div>
		{:else}
			<div class="muted">Search and add phrases above to build a merge.</div>
		{/if}
	</div>

	<div class="dest">
		<div class="dest-choice">
			<label class="radio"><input type="radio" bind:group={mode} value="new" /> New canonical</label>
			<label class="radio"><input type="radio" bind:group={mode} value="existing" /> Add to existing group</label>
		</div>
		{#if mode === 'new'}
			<div class="dest-fields">
				<input type="text" bind:value={newName} list="existing-canonicals" autocomplete="off" placeholder="canonical name…" />
				<select bind:value={category}>
					<option value="" disabled>Category…</option>
					{#each data.categories as c (c)}<option value={c}>{c}</option>{/each}
				</select>
			</div>
		{:else}
			<div class="dest-fields">
				<select bind:value={groupCanonical}>
					<option value="" disabled>Pick a group…</option>
					{#each data.merges as m (m.canonical)}<option value={m.canonical}>{m.canonical} ({n(m.usage)})</option>{/each}
				</select>
				{#if groupCanonical}
					{#if groupCategory}
						<span class="inherit">inherits <span class="pill">{groupCategory}</span></span>
					{:else}
						<select bind:value={category}>
							<option value="" disabled>Category…</option>
							{#each data.categories as c (c)}<option value={c}>{c}</option>{/each}
						</select>
					{/if}
				{/if}
			</div>
		{/if}
	</div>

	<form method="post" action="?/merge" use:enhance={onMerged} class="b-go">
		{#each basket as b (b)}<input type="hidden" name="aliases" value={b} />{/each}
		<input type="hidden" name="threshold" value={data.threshold} />
		<input type="hidden" name="canonical" value={targetCanonical} />
		<input type="hidden" name="category" value={effectiveCategory} />
		<button type="submit" disabled={!canMerge}>
			Merge{basket.length ? ` ${basket.length} phrase${basket.length === 1 ? '' : 's'}` : ''}{#if canMerge} {mode === 'new' ? `into “${newName.trim()}”` : `into “${groupCanonical}”`}{/if}
		</button>
	</form>
</div>

<!-- ── Suggested clusters (embeddings) ────────────────────────────────── -->
<h3>Suggested clusters ({data.clusters.length}) <Hint text="Groups of taxonomy phrases whose embeddings are similar above the chosen similarity threshold. Higher threshold = tighter, fewer groups. Open one in the builder to name it and pick a category." /></h3>
<form class="threshold" method="get">
	<label for="thr">Similarity</label>
	<input
		id="thr"
		type="range"
		name="threshold"
		min="0.5"
		max="0.95"
		step="0.05"
		value={data.threshold}
		onchange={(e) => e.currentTarget.form?.requestSubmit()}
	/>
	<strong class="thr-val">{data.threshold.toFixed(2)}</strong>
	<span class="muted thr-desc">{data.threshold >= 0.85 ? 'tight · fewer, cleaner groups' : data.threshold <= 0.6 ? 'loose · more, looser groups' : 'balanced'}</span>
</form>
{#each data.clusters as cluster, i (i)}
	<div class="panel cluster">
		<div class="cluster-members">
			{#each cluster.members as m (m.phrase)}
				<span class="member">{m.phrase} <span class="muted">{n(m.usage)}</span></span>
			{/each}
		</div>
		<a class="open-btn" data-sveltekit-reload href={clusterLink(cluster.members.map((m) => m.phrase))}>Open in builder ▸</a>
	</div>
{:else}
	<div class="panel">No clusters at this threshold. Lower it to surface looser groupings.</div>
{/each}

<!-- ── Active merges ──────────────────────────────────────────────────── -->
<h3>Active merges ({data.merges.length}) <Hint text="Merges currently in effect. Everywhere in Explore, these phrases are counted as their canonical form. Use + add to put more phrases into a group, or Unmerge to undo." /></h3>
<div class="table-card">
{#if data.merges.length}
<div class="table-scroll">
	<table>
		<thead><tr><th>Canonical <Hint text="The single phrase the merged variants now report as." /></th><th>Merged phrases <Hint text="The alias phrases folded into the canonical." /></th><th class="num">Combined usage <Hint text="Total comment_indicators rows across the canonical and all its merged variants." /></th><th></th></tr></thead>
		<tbody>
			{#each data.merges as m (m.canonical)}
				<tr>
					<td><strong>{m.canonical}</strong>{#if m.category}<span class="pill" style="margin-left:6px">{m.category}</span>{/if}</td>
					<td>{m.members.join(', ')}</td>
					<td class="num">{n(m.usage)}</td>
					<td class="row-actions">
						<a class="builder-link" data-sveltekit-reload href={intoLink(m.canonical)}>+ add</a>
						<form method="post" action="?/unmerge" use:enhance>
							<input type="hidden" name="canonical" value={m.canonical} />
							<button class="ghost" title="Undo merge">Unmerge</button>
						</form>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{:else}
<div class="table-empty">No active merges yet. Build one above, or fold a suggested cluster.</div>
{/if}
</div>

<style>
	.builder {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.b-search {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		max-width: 420px;
	}
	.muted {
		color: var(--muted);
		font-size: var(--text-sm);
	}
	.muted.pad {
		padding: var(--space-2);
	}
	.cand-list {
		max-height: 240px;
		overflow-y: auto;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		background: var(--surface-2);
	}
	.cand {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		width: 100%;
		text-align: left;
		padding: 4px var(--space-3);
		border: none;
		border-bottom: 1px solid var(--border);
		background: transparent;
		color: var(--text);
		font-size: var(--text-sm);
		cursor: pointer;
	}
	.cand:last-child {
		border-bottom: none;
	}
	.cand:hover {
		background: var(--accent-dim);
	}
	.cand-add {
		flex: 1;
	}
	.seed-dot {
		color: var(--accent);
		font-size: var(--text-2xs);
	}
	.basket {
		border: 1px dashed var(--border);
		border-radius: var(--radius-sm);
		padding: var(--space-3);
	}
	.basket-head {
		font-size: var(--text-xs);
		color: var(--muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-bottom: var(--space-2);
	}
	.basket-items {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.bchip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 2px 8px;
		border: 1px solid var(--border);
		border-left: 3px solid var(--accent);
		border-radius: 6px;
		background: var(--surface);
		font-size: var(--text-sm);
	}
	.bchip-x {
		border: none;
		background: transparent;
		color: var(--muted);
		font-size: var(--text-2xs);
		cursor: pointer;
		padding: 0;
	}
	.bchip-x:hover {
		color: var(--danger);
	}
	.preview {
		margin-top: var(--space-2);
		font-size: var(--text-sm);
		color: var(--text);
	}
	.dest {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-top: var(--space-3);
		border-top: 1px solid var(--border);
	}
	.dest-choice {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
	}
	.radio {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: var(--text-sm);
		cursor: pointer;
	}
	.radio input {
		accent-color: var(--accent);
	}
	.dest-fields {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-3);
	}
	.inherit {
		font-size: var(--text-sm);
		color: var(--muted);
	}
	.b-go {
		margin: 0;
	}
	.builder-link {
		display: inline-block;
		margin-top: var(--space-2);
		font-size: var(--text-xs);
	}
	.row-actions {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		white-space: nowrap;
	}
	/* Similarity slider — a compact inline control under the Suggested clusters heading. */
	.threshold {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-3);
		margin: 0 0 var(--space-4);
		font-size: var(--text-sm);
		color: var(--muted);
	}
	.threshold label {
		text-transform: uppercase;
		letter-spacing: 0.04em;
		font-size: var(--text-xs);
	}
	.threshold input[type='range'] {
		flex: 1;
		min-width: 150px;
		max-width: 280px;
		accent-color: var(--accent);
	}
	.thr-val {
		color: var(--text);
		font-variant-numeric: tabular-nums;
	}
	.thr-desc {
		font-size: var(--text-xs);
	}
	/* Suggested cluster: just the member phrases + an Open-in-builder button. */
	.cluster {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: var(--space-4);
	}
	.cluster-members {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		flex: 1;
		min-width: 200px;
	}
	.member {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 2px 8px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--surface-2);
		font-size: var(--text-sm);
	}
	.open-btn {
		flex: none;
		padding: 5px 12px;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		background: var(--surface);
		color: var(--text);
		font-size: var(--text-sm);
		white-space: nowrap;
	}
	.open-btn:hover {
		border-color: var(--accent);
		color: var(--accent);
		text-decoration: none;
	}
</style>
