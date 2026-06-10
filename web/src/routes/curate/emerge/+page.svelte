<script lang="ts">
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';
	import Hint from '$lib/Hint.svelte';
	import { n } from '$lib/format';
	let { data, form } = $props();

	const snap = $derived(data.snapshot);
	// Deliberately seeded ONCE from the stored snapshot (the slider is the user's
	// draft for the next recompute, not a mirror of the saved value).
	let threshold = $state(untrack(() => data.snapshot?.threshold ?? 0.7));
	let recomputing = $state(false);

	const fmtDate = (iso: string) => iso.slice(0, 10);
	const anchorDate = (utc: number) => new Date(utc * 1000).toISOString().slice(0, 10);
	const recentPct = (recent: number, citations: number) =>
		citations ? Math.round((100 * recent) / citations) : 0;

	// Deep-link into the Merge builder (same ?sel contract as its own suggested
	// clusters; full reload so the builder re-seeds from the URL). sel is capped
	// for URL-length safety — the builder's search can pull in the rest.
	const SEL_CAP = 20;
	const builderLink = (phrases: string[]) => {
		const p = new URLSearchParams();
		for (const m of phrases.slice(0, SEL_CAP)) p.append('sel', m);
		p.set('threshold', String(snap?.threshold ?? 0.7));
		return `/curate/merge?${p}#builder`;
	};
	const searchLink = (phrase: string) =>
		`/curate/indicators?search=${encodeURIComponent(phrase)}&mode=both`;
</script>

<h2>Emerging</h2>
<p class="page-desc">
	Uncategorised phrases — the ones <em>no existing seed matched</em>, which is exactly where a new
	tell first shows up — clustered by embedding similarity and ranked by recency-weighted citations.
	This view is read-only: act on a cluster in the <a href="/curate/merge">Merge builder</a> (name
	it, pick a category) or on a single phrase via the <a href="/curate/indicators">Categorise</a>
	screen.
</p>

{#if form?.message}
	<div class="flash success">{form.message}</div>
{/if}

{#if !data.embeddingsReady}
	<div class="panel">
		<strong>No phrase embeddings yet.</strong> This view clusters the raw cue phrases by their
		embeddings, which the pipeline persists since schema v9. Run
		<code>isthisai-embed categorize</code> (or <code>ground</code>) once to populate them, then
		recompute here.
	</div>
{:else}
	<form
		class="threshold panel"
		method="post"
		action="?/recompute"
		use:enhance={() => {
			recomputing = true;
			return async ({ update }) => {
				recomputing = false;
				await update();
			};
		}}
	>
		<label for="thr">Similarity</label>
		<input id="thr" type="range" name="threshold" min="0.5" max="0.95" step="0.05" bind:value={threshold} />
		<strong class="thr-val">{Number(threshold).toFixed(2)}</strong>
		<button type="submit" disabled={recomputing}>
			{recomputing ? 'Recomputing…' : 'Recompute clusters'}
		</button>
		<span class="muted">takes a few seconds; result is stored until the next recompute</span>
	</form>

	{#if snap}
		<!-- Provenance: never let a capped computation read as "everything". -->
		<p class="provenance">
			Clustered the top <strong>{n(snap.poolSize)}</strong> of
			<strong>{n(snap.eligible)}</strong> uncategorised phrases by recency score (8-week
			half-life) · threshold {snap.threshold.toFixed(2)} · computed {fmtDate(snap.computedAt)} ·
			decay anchored to {anchorDate(snap.anchorUtc)}.
			{#if snap.missingEmbeddings > 0}
				{n(snap.missingEmbeddings)} phrases have no embedding yet — run
				<code>isthisai-embed categorize</code> to include them.
			{/if}
		</p>

		<h3>
			Clusters ({snap.clusters.length})
			<Hint
				text="Groups of ≥2 uncategorised phrases with similar embeddings — likely the same underlying tell, phrased differently. Score is the sum of recency-decayed citations (a citation today counts 1, an 8-week-old one 0.5); 'recent' is the share of citations from the last 8 weeks, so you can see WHY something ranks."
			/>
		</h3>
		{#each snap.clusters as cluster, i (i)}
			<div class="panel cluster">
				<div class="cluster-head">
					<span class="rank">#{i + 1}</span>
					<span class="score" title="Sum of recency-decayed citations across members">{cluster.score.toFixed(1)}</span>
					<span class="muted">{n(cluster.citations)} citations · {recentPct(cluster.recent, cluster.citations)}% in the last 8 weeks</span>
				</div>
				<div class="cluster-members">
					{#each cluster.members as m (m.phrase)}
						<a class="member" href={searchLink(m.phrase)} title="Open in Categorise (search)">
							{m.phrase} <span class="muted">{n(m.citations)}×{#if m.recent} · {m.recent} recent{/if}</span>
						</a>
					{/each}
				</div>
				<a class="open-btn" data-sveltekit-reload href={builderLink(cluster.members.map((m) => m.phrase))}>
					Open in builder ▸{#if cluster.members.length > SEL_CAP} <span class="muted">(first {SEL_CAP} of {cluster.members.length})</span>{/if}
				</a>
			</div>
		{:else}
			<div class="panel">No clusters at this threshold. Lower it to surface looser groupings.</div>
		{/each}

		{#if snap.unclustered.length}
			<h3>
				Top unclustered phrases
				<Hint
					text="High-scoring phrases that joined no cluster. A brand-new tell often has exactly one phrasing at first, so the newest signals can appear here before they ever form a cluster. Click to curate via search."
				/>
			</h3>
			<div class="panel cluster-members">
				{#each snap.unclustered as m (m.phrase)}
					<a class="member" href={searchLink(m.phrase)} title="Open in Categorise (search)">
						{m.phrase} <span class="muted">{m.score.toFixed(1)} · {n(m.citations)}×</span>
					</a>
				{/each}
			</div>
		{/if}
	{:else}
		<div class="panel">
			No snapshot yet — hit <strong>Recompute clusters</strong> above to build the first one.
		</div>
	{/if}
{/if}

<style>
	/* Threshold + recompute control (clones the Merge page's slider treatment). */
	.threshold {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-3);
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
	.provenance {
		font-size: var(--text-xs);
		color: var(--muted);
		margin: var(--space-3) 0 var(--space-4);
	}
	.cluster {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: var(--space-4);
	}
	.cluster-head {
		flex: 0 0 100%;
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		font-size: var(--text-sm);
	}
	.rank {
		color: var(--muted);
		font-size: var(--text-xs);
	}
	.score {
		font-weight: 700;
		color: var(--accent);
		font-variant-numeric: tabular-nums;
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
		color: var(--text);
		text-decoration: none;
	}
	.member:hover {
		border-color: var(--accent);
		text-decoration: none;
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
