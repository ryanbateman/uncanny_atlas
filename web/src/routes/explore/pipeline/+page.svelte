<script lang="ts">
	import Hint from '$lib/Hint.svelte';
	import { n } from '$lib/format';
	let { data } = $props();
	const s = $derived(data.status);

	const pctOf = (num: number, den: number) => (den ? (num / den) * 100 : 0);
	// Bar width is proportional to the whole corpus, so the funnel's narrowing is
	// literal; a small floor keeps tiny stages visible.
	const barW = (count: number) => Math.max(pctOf(count, s.totalComments), 1.2);

	const stages = $derived([
		{
			name: 'Collected',
			count: s.totalComments,
			pct: 100,
			unit: 'the whole corpus',
			hint: 'Every comment fetched from r/isthisAI + r/RealOrAI — the universe indicators are drawn from.'
		},
		{
			name: 'Embedded',
			count: s.embeddedComments,
			pct: pctOf(s.embeddedComments, s.totalComments),
			unit: 'of collected',
			hint: 'Comments mapped to a vector. Embedding the whole corpus is what lets semantic expansion reach beyond the read sample — at 100% there is no embedding gap.'
		},
		{
			name: 'Candidate comments',
			count: s.candidateComments,
			pct: pctOf(s.candidateComments, s.totalComments),
			unit: 'of collected',
			hint: 'Comments that could plausibly name a visual indicator: they pass a keyword + length (≥20 chars) + non-bot filter. The rest are bot boilerplate, one-word reactions, jokes, or off-topic — they were never going to cite an indicator.'
		},
		{
			name: 'Read by the model',
			count: s.llmSample,
			pct: pctOf(s.llmSample, s.candidateComments),
			unit: 'of candidates',
			hint: 'The sampled comments the LLM (gemma3) read directly, one per call, summed across every extraction run (per-run sizes are in the runs table below). Reading is slow, so only a sample is read each time — semantic expansion then covers the rest of the candidates cheaply.'
		},
		{
			name: 'Comments citing an indicator',
			count: s.analysedComments,
			pct: pctOf(s.analysedComments, s.semanticEligible),
			unit: 'of eligible',
			extra: `${pctOf(s.analysedComments, s.totalComments).toFixed(1)}% of all`,
			hint: 'Comments with at least one concrete visual indicator, found by the LLM, semantic expansion, or keyword match. Semantic expansion is gated to comments ≥20 chars / non-bot (the same length floor as the sample), so it cannot pad this with one-word or emoji reactions. Most comments just react ("obviously AI") without naming a specific indicator, so this is the natural rate — not a processing backlog.'
		}
	]);
</script>

<h2>Pipeline status</h2>
<p class="page-desc">
	How the corpus narrows from every collected comment down to the ones that name a specific visual
	indicator — and how those indicators were found. A read-only snapshot of extraction, embedding, and expansion.
</p>

{#if data.pending.count > 0}
	<div class="flash nudge">
		<strong>{n(data.pending.count)}</strong> indicator{data.pending.count === 1 ? '' : 's'}
		(re)categorised since the last expansion. Run <code>uv run isthisai-embed semantic</code> to gather
		their comments — your earlier Noise/category decisions are respected.
	</div>
{/if}

<h3>Coverage funnel <Hint text="Each stage narrows the one above it. Percentages are shown against the most meaningful denominator for that step (the corpus, or the candidate set), and bar widths are proportional to the whole corpus." /></h3>
<div class="funnel">
	{#each stages as stage (stage.name)}
		<div class="stage">
			<div class="stage-head">
				<span class="stage-name">{stage.name} <Hint text={stage.hint} /></span>
				<span class="stage-val">
					{n(stage.count)}
					<span class="stage-pct">· {stage.pct.toFixed(1)}% {stage.unit}{#if stage.extra}, {stage.extra}{/if}</span>
				</span>
			</div>
			<div class="track"><div class="fill" style="width:{barW(stage.count)}%"></div></div>
		</div>
	{/each}
</div>

<h3>Candidate keyword filter <Hint text="A comment is a candidate only if its text contains at least one of these terms (and is ≥20 characters, and isn't a known bot). Deliberately broad — better to over-include than miss a real detection; the indicator extraction downstream is what makes it precise." /></h3>
<p class="page-desc">
	The keyword pre-filter that defines the <strong>candidate comments</strong> stage above (the pool the
	LLM samples from). A comment must mention at least one of these (plus the ≥20-char and non-bot checks).
	<strong>Semantic expansion</strong> uses a broader gate — the same ≥20-char / non-bot checks but
	<em>no</em> keyword requirement, so it can reach comments that describe a tell without these words:
	<strong>{n(s.semanticEligible)}</strong> eligible comments. The ≥20-char floor is what stops it
	matching one-word & emoji reactions (a generic seed like "AI voice" would otherwise vacuum up thousands).
</p>
<div class="pill-list keywords">
	{#each s.opinionKeywords as kw (kw)}<span class="pill">{kw}</span>{/each}
</div>

<h3>How the indicators were found <Hint text="Indicator ROWS by source (not comments). A single comment can carry several indicators, so these sum to more than the 'comments citing an indicator' stage above." /></h3>
<div class="cards">
	<div class="card"><div class="value">{n(s.llm)}</div><div class="label">LLM-extracted <Hint text="Rows the LLM produced while reading the sampled comments." /></div></div>
	<div class="card"><div class="value">{n(s.semantic)}</div><div class="label">Semantic matches <Hint text="Rows added by embedding similarity (batch_id semantic_*) — how coverage grows past the read sample. Restricted to comments ≥20 chars / non-bot (same length gate as the LLM sample), so one-word & emoji reactions are excluded." /></div></div>
	<div class="card"><div class="value">{n(s.keyword)}</div><div class="label">Keyword expansion <Hint text="Rows added by keyword matching (batch_id keyword_*)." /></div></div>
</div>

<h3>Taxonomy &amp; curation</h3>
<div class="cards">
	<div class="card"><div class="value">{n(s.taxonomy)}</div><div class="label">Taxonomy indicators <Hint text="Distinct indicators in the taxonomy — the source of truth for categories and semantic matching." /></div></div>
	<div class="card"><div class="value">{n(s.embeddedIndicators)}</div><div class="label">Embedded indicators <Hint text="Taxonomy indicators with a vector embedding (required before semantic expansion can match them)." /></div></div>
	<div class="card"><div class="value">{n(s.aliases)}</div><div class="label">Indicator aliases <Hint text="Alias → canonical mappings from Curate → Merge. Each collapses a phrasing into a canonical indicator." /></div></div>
	<div class="card"><div class="value">{n(data.pending.count)}</div><div class="label">Pending re-expansion <Hint text="Indicators (re)categorised to a real category since the last semantic run. Re-run isthisai-embed semantic to gather comments for them." /></div></div>
</div>

<h3>Recent extraction runs <Hint text="The last 10 LLM extraction batches, with the model used, timing, and how many comments each processed." /></h3>
<div class="table-card">
{#if s.runs.length}
<div class="table-scroll">
	<table>
		<thead>
			<tr><th>Batch</th><th>Model</th><th>Started</th><th>Completed</th><th class="num">Sample</th><th class="num">Processed</th></tr>
		</thead>
		<tbody>
			{#each s.runs as r (r.batch_id)}
				<tr>
					<td class="truncate" style="max-width:200px" title={r.batch_id}>{r.batch_id}</td>
					<td>{r.model}</td>
					<td>{r.started_at ?? '—'}</td>
					<td>{r.completed_at ?? '—'}</td>
					<td class="num">{r.sample_size ?? '—'}</td>
					<td class="num">{r.comments_processed ?? '—'}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{:else}
<div class="table-empty">No extraction runs recorded.</div>
{/if}
</div>

<style>
	.funnel {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-5);
	}
	.stage-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--space-3);
		margin-bottom: 4px;
	}
	.stage-name {
		font-weight: 600;
	}
	.stage-val {
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.stage-pct {
		color: var(--muted);
		font-size: var(--text-xs);
		font-weight: 400;
	}
	.track {
		height: 12px;
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: 999px;
		overflow: hidden;
	}
	.fill {
		height: 100%;
		background: linear-gradient(90deg, #76b7b2, var(--accent));
		border-radius: 999px;
		transition: width 0.4s;
	}
	.keywords {
		margin-bottom: var(--space-5);
	}
</style>
