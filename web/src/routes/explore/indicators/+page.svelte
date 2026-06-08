<script lang="ts">
	import Plot from '$lib/Plot.svelte';
	import Figure from '$lib/Figure.svelte';
	import Hint from '$lib/Hint.svelte';
	import SelfHostNotice from '$lib/SelfHostNotice.svelte';
	import { n } from '$lib/format';
	import {
		CATEGORY_SCHEME,
		CHART_STYLE,
		BAR_BLUE,
		BAR_TEAL,
		LINE_PALETTE,
		spines,
		seriesMark,
		seriesY,
		timeGrid,
		timeTicks,
		type SeriesMode
	} from '$lib/chart';
	let { data } = $props();

	// Per-chart controls (instant). Granularity switches between the pre-computed
	// week/month datasets; mode switches line / stacked / 100%; the category charts
	// each have their own "Show noise" toggle (filters the Noise category in/out).
	let otGran = $state<'week' | 'month'>('month');
	let topGran = $state<'week' | 'month'>('month');
	let otMode = $state<SeriesMode>('stacked');
	let topMode = $state<SeriesMode>('stacked');
	let catNoise = $state(false);
	let otNoise = $state(false);
	let subNoise = $state(false);

	const toDate = (iso: string) => new Date(iso + 'T00:00:00Z');
	// Shared continuous UTC domain (fixed start, no gaps), matching the Overview
	// over-time charts so every time axis in the app lines up.
	const xDomain = $derived(
		data.domain ? [toDate(data.domain.min), toDate(data.domain.max)] : undefined
	);

	// Category-decomposition charts ship with the Noise category; drop it unless the
	// chart's "Show noise" toggle is on.
	const categoryData = $derived(
		catNoise ? data.categoryCounts : data.categoryCounts.filter((r) => r.category !== 'Noise')
	);
	const bySubData = $derived(
		subNoise ? data.bySubreddit : data.bySubreddit.filter((r) => r.category !== 'Noise')
	);

	// Densify the selected-granularity series over its contiguous bucket list:
	// stacked/normalized areas misrender when a category is absent for some periods.
	// Fill every bucket × category with 0, keep a stable category order (largest
	// first), and carry a real Date for the time scale.
	const otData = $derived.by(() => {
		let rows = data.overTime[otGran] as { period: string; category: string; count: number }[];
		if (!otNoise) rows = rows.filter((r) => r.category !== 'Noise');
		const totals = new Map<string, number>();
		for (const r of rows) totals.set(r.category, (totals.get(r.category) ?? 0) + r.count);
		const categories = [...totals.keys()].sort((a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0));
		const have = new Map(rows.map((r) => [`${r.period} ${r.category}`, r.count]));
		const dense: { period: string; date: Date; category: string; count: number }[] = [];
		for (const p of data.periods[otGran])
			for (const c of categories)
				dense.push({ period: p, date: toDate(p), category: c, count: have.get(`${p} ${c}`) ?? 0 });
		return { dense, categories };
	});

	// Top-indicator series for the selected granularity (densified server-side),
	// with a Date attached for the time scale.
	const topData = $derived(data.topOverTime[topGran]);
	const topSeries = $derived(topData.series.map((r) => ({ ...r, date: toDate(r.period) })));
</script>

<h2>Top Indicators</h2>
<p class="page-desc">
	What indicators people cite when judging whether an image is AI. Counts are in <strong>mentions</strong> — one
	per indicator per comment. A single comment can mention several indicators across several categories, so category totals sum to more than the number of comments. Phrases are alias-resolved, so merged
	indicators (see Curate → Merge) collapse into their canonical form (e.g. '3 hands' and 'weird hands' may have been merged, and each counted simply toward 'Hands'). 
	The two over-time charts go a step further: each post is counted once per indicator (not once per comment), so a single viral post can't dominate a trend.
</p>

<Figure
	title="Top 10 indicators over time"
	hint="The 10 most-cited individual indicators overall (by distinct comments), each tracked over time. Switch between line, stacked area, or 100% stacked to compare the mix. It effectively starts in 2025 because indicators are sampled from comments, and ~99.8% of comments are from 2025 onward — the subreddits were tiny until AI images went mainstream (r/RealOrAI near-dormant until mid-2023, r/isthisAI launched 2024)."
	caption="The ten most-cited indicators overall, each tracked over time. Click a name in the legend to inspect that indicator."
>
	{#snippet controls()}
		<select bind:value={topGran} class="chart-mode" aria-label="Granularity">
			<option value="week">Week</option>
			<option value="month">Month</option>
		</select>
		<select bind:value={topMode} class="chart-mode" aria-label="Chart mode">
			<option value="line">Line</option>
			<option value="stacked">Stacked area</option>
			<option value="percent">100% stacked</option>
		</select>
	{/snippet}
	<div class="chart-legend">
		{#each topData.indicators as ind, i (ind)}
			<a href="/explore/lookup?indicator={encodeURIComponent(ind)}">
				<span class="swatch" style="background:{LINE_PALETTE[i % LINE_PALETTE.length]}"></span>{ind}{#if data.mergeGroups[ind]?.length}<span class="merge-badge canon" title="Merged from {data.mergeGroups[ind].length} phrase(s): {data.mergeGroups[ind].join(', ')}">{data.mergeGroups[ind].length} merged</span>{/if}
			</a>
		{/each}
	</div>
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				height: 460,
				marginLeft: 55,
				marginBottom: 34,
				x: { type: 'utc', domain: xDomain, label: null, axis: null },
				y: seriesY(topMode, 'comments'),
				color: { legend: false, domain: topData.indicators, range: LINE_PALETTE },
				marks: [
					...timeGrid(P, topGran),
					seriesMark(P, topSeries, { x: 'date', y: 'count', series: 'indicator', mode: topMode }),
					...spines(P),
					...timeTicks(P, topGran)
				]
			})}
	/>
</Figure>

<h3>Top indicators <Hint text="The most-cited individual indicators, alias-resolved so merged phrases (Curate → Merge) are combined into one canonical entry." /></h3>
<div class="table-card">
{#if data.top.length}
<div class="table-scroll">
	<table>
		<thead><tr><th>Indicator</th><th>Category</th><th class="num">Comments <Hint text="Distinct comments that cite this indicator (counting each comment once, summed across merged variants)." /></th></tr></thead>
		<tbody>
			{#each data.top as row (row.indicator)}
				<tr>
					<td><a href="/explore/lookup?indicator={encodeURIComponent(row.indicator)}">{row.indicator}</a>{#if data.mergeGroups[row.indicator]?.length}<span class="merge-badge canon" style="margin-left:6px" title="Merged from {data.mergeGroups[row.indicator].length} phrase(s): {data.mergeGroups[row.indicator].join(', ')}">{data.mergeGroups[row.indicator].length} merged</span>{/if}</td>
					<td><span class="pill">{row.category}</span></td>
					<td class="num">{n(row.count)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{:else}
<div class="table-empty">No indicators yet.</div>
{/if}
</div>

<Figure
	title="Mentions by category"
	hint="A mention = one comment associated with an indicator (via LLM extraction, semantic expansion, or keyword expansion). Here they're grouped into the 8 taxonomy categories."
	caption="Total mentions in each taxonomy category. A comment can contribute to several categories. Noise = phrases marked as non-indicators; toggle it in with Show noise."
>
	{#snippet controls()}
		<label class="chart-toggle"><input type="checkbox" bind:checked={catNoise} /> Show noise</label>
	{/snippet}
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				marginLeft: 110,
				x: { grid: true, label: 'mentions' },
				y: { label: null },
				marks: [
					P.barX(categoryData, { x: 'count', y: 'category', sort: { y: '-x' }, fill: BAR_BLUE, tip: true }),
					...spines(P)
				]
			})}
	/>
</Figure>

<Figure
	title="Mentions over time"
	hint="Indicator mentions per time bucket, stacked by category — shows which kinds of indicators trend up or down. Toggle 100% to compare each period's category mix regardless of total volume. The trend effectively starts in 2025: r/RealOrAI was near-dormant until mid-2023 and r/isthisAI only launched in 2024, so ~99.8% of all comments — and the indicators sampled from them — are from 2025 onward. That's why the chart looks empty before then."
	caption="Mentions per bucket, stacked by category. Toggle 100% to compare each period's mix regardless of volume."
>
	{#snippet controls()}
		<label class="chart-toggle"><input type="checkbox" bind:checked={otNoise} /> Show noise</label>
		<select bind:value={otGran} class="chart-mode" aria-label="Granularity">
			<option value="week">Week</option>
			<option value="month">Month</option>
		</select>
		<select bind:value={otMode} class="chart-mode" aria-label="Chart mode">
			<option value="line">Line</option>
			<option value="stacked">Stacked area</option>
			<option value="percent">100% stacked</option>
		</select>
	{/snippet}
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				marginLeft: 55,
				marginBottom: 34,
				x: { type: 'utc', domain: xDomain, label: null, axis: null },
				y: seriesY(otMode, 'mentions'),
				color: { legend: true, scheme: CATEGORY_SCHEME, domain: otData.categories },
				marks: [
					...timeGrid(P, otGran),
					seriesMark(P, otData.dense, { x: 'date', y: 'count', series: 'category', mode: otMode }),
					...spines(P),
					...timeTicks(P, otGran)
				]
			})}
	/>
</Figure>

<Figure
	title="Mentions by subreddit"
	hint="Category mentions split by subreddit, so you can compare what each community focuses on."
	caption="Category mentions split by subreddit, to compare what each community focuses on."
>
	{#snippet controls()}
		<label class="chart-toggle"><input type="checkbox" bind:checked={subNoise} /> Show noise</label>
	{/snippet}
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				marginLeft: 110,
				x: { grid: true, label: 'mentions' },
				y: { label: null },
				color: { legend: true, scheme: CATEGORY_SCHEME },
				marks: [
					P.barX(bySubData, { x: 'count', y: 'category', fill: 'subreddit', sort: { y: '-x' }, tip: true }),
					...spines(P)
				]
			})}
	/>
</Figure>

<Figure
	title="How indicators were found"
	hint="Where each indicator row came from: LLM Extraction (the sampled comments the model read), Semantic (added by embedding similarity), or Keyword Expansion (added by keyword match)."
	caption="Where each indicator row came from — LLM extraction, semantic expansion, or keyword match."
>
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				height: 150,
				marginLeft: 130,
				x: { grid: true, label: 'rows' },
				y: { label: null },
				marks: [
					P.barX(data.sources, { x: 'count', y: 'source', sort: { y: '-x' }, fill: BAR_TEAL, tip: true }),
					...spines(P)
				]
			})}
	/>
</Figure>

<h3>Example comments <Hint text="The highest-scoring comments that cite an indicator in the chosen category, with the matched indicator(s) shown." /></h3>
{#if data.readonly}
	<SelfHostNotice what="Example comments" />
{:else}
<div class="table-card">
	<form class="filter-bar table-controls" method="get">
		<label>
			Category
			<select name="category" onchange={(e) => e.currentTarget.form?.requestSubmit()}>
				{#each data.categories as c (c)}
					<option value={c} selected={c === data.category}>{c}</option>
				{/each}
			</select>
		</label>
	</form>
	{#if data.examples.length}
	<div class="table-scroll">
		<table>
			<thead><tr><th>Indicator</th><th>Comment</th><th>Sub</th><th class="num">Score</th></tr></thead>
			<tbody>
				{#each data.examples as ex (ex.id)}
					<tr>
						<td>{ex.indicator}</td>
						<td class="truncate" title={ex.body}>{ex.body}</td>
						<td>{ex.subreddit}</td>
						<td class="num">{n(ex.score ?? 0)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{:else}
	<div class="table-empty">No example comments in this category.</div>
	{/if}
</div>
{/if}
