<script lang="ts">
	import Plot from '$lib/Plot.svelte';
	import Figure from '$lib/Figure.svelte';
	import Hint from '$lib/Hint.svelte';
	import MediaSelect from '$lib/MediaSelect.svelte';
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
	// Per-chart/table media filters ('' = All). Server rows carry a media
	// dimension; filtering selects it, All sums it away — exact, because each
	// comment/post belongs to exactly one submission, hence one media type.
	let topMedia = $state('');
	let tableMedia = $state('');
	let catMedia = $state('');
	let otMedia = $state('');
	let bySubMedia = $state('');

	const toDate = (iso: string) => new Date(iso + 'T00:00:00Z');
	// Shared continuous UTC domain (fixed start, no gaps), matching the Overview
	// over-time charts so every time axis in the app lines up.
	const xDomain = $derived(
		data.domain ? [toDate(data.domain.min), toDate(data.domain.max)] : undefined
	);

	// Filter rows by media, then sum the media dimension away, grouped by `key`.
	function byMedia<T extends { media: string; count: number }>(
		rows: T[],
		media: string,
		key: (r: T) => string
	): Map<string, { row: T; count: number }> {
		const out = new Map<string, { row: T; count: number }>();
		for (const r of rows) {
			if (media && r.media !== media) continue;
			const k = key(r);
			const cur = out.get(k);
			if (cur) cur.count += r.count;
			else out.set(k, { row: r, count: r.count });
		}
		return out;
	}

	// Category-decomposition charts ship with the Noise category; drop it unless the
	// chart's "Show noise" toggle is on. Media filter first, then noise.
	const categoryData = $derived.by(() => {
		const agg = [...byMedia(data.categoryCounts, catMedia, (r) => r.category).values()].map(
			({ row, count }) => ({ category: row.category, count })
		);
		return catNoise ? agg : agg.filter((r) => r.category !== 'Noise');
	});
	const bySubData = $derived.by(() => {
		const agg = [
			...byMedia(data.bySubreddit, bySubMedia, (r) => `${r.category}|${r.subreddit}`).values()
		].map(({ row, count }) => ({ category: row.category, subreddit: row.subreddit, count }));
		return subNoise ? agg : agg.filter((r) => r.category !== 'Noise');
	});

	// Densify the selected-granularity series over its contiguous bucket list:
	// stacked/normalized areas misrender when a category is absent for some periods.
	// Fill every bucket × category with 0, keep a stable category order (largest
	// first), and carry a real Date for the time scale.
	const otData = $derived.by(() => {
		let rows = [...byMedia(data.overTime[otGran], otMedia, (r) => `${r.period}|${r.category}`).values()].map(
			({ row, count }) => ({ period: row.period, category: row.category, count })
		);
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

	// Top-10 over time: the server ships SPARSE (period, indicator, media) rows
	// for the union of every facet's top 10. Filter to the selected media, rank
	// that facet's own top 10, then densify over the contiguous bucket list
	// (this densify loop used to run server-side; it moved here with the filter).
	const topData = $derived.by(() => {
		const agg = [
			...byMedia(data.topOverTime[topGran].rows, topMedia, (r) => `${r.period}|${r.indicator}`).values()
		].map(({ row, count }) => ({ period: row.period, indicator: row.indicator, count }));
		const totals = new Map<string, number>();
		for (const r of agg) totals.set(r.indicator, (totals.get(r.indicator) ?? 0) + r.count);
		const indicators = [...totals.entries()]
			.sort((a, b) => b[1] - a[1])
			.slice(0, 10)
			.map((e) => e[0]);
		const keep = new Set(indicators);
		const have = new Map<string, number>();
		for (const r of agg) if (keep.has(r.indicator)) have.set(`${r.period} ${r.indicator}`, r.count);
		const series: { period: string; date: Date; indicator: string; count: number }[] = [];
		for (const p of data.periods[topGran])
			for (const ind of indicators)
				series.push({ period: p, date: toDate(p), indicator: ind, count: have.get(`${p} ${ind}`) ?? 0 });
		return { series, indicators };
	});
	const topSeries = $derived(topData.series);

	// Top table: re-rank the (canonical, media) rows for the selected media.
	// Category is media-invariant in practice; take the max across an
	// indicator's rows for a stable pill (mirrors the SQL's MAX(ci.category)).
	const tableRows = $derived.by(() => {
		const counts = new Map<string, { count: number; category: string }>();
		for (const r of data.top) {
			if (tableMedia && r.media !== tableMedia) continue;
			const cur = counts.get(r.indicator);
			if (cur) {
				cur.count += r.count;
				if (r.category > cur.category) cur.category = r.category;
			} else counts.set(r.indicator, { count: r.count, category: r.category });
		}
		return [...counts.entries()]
			.map(([indicator, v]) => ({ indicator, ...v }))
			.sort((a, b) => b.count - a.count)
			.slice(0, 40);
	});
</script>

<h2>Top Indicators</h2>
<p class="page-desc">
	What indicators people cite when judging whether an image is AI. Counts are in <strong>mentions</strong> — one
	per indicator per comment. A single comment can mention several indicators across several categories, so category totals sum to more than the number of comments. Phrases are alias-resolved, so merged
	indicators (see Curate → Merge) collapse into their canonical form (e.g. '3 hands' and 'weird hands' may have been merged, and each counted simply toward 'Hands'). 
	The two over-time charts go a step further: each post is counted once per indicator (not once per comment), so a single viral post can't dominate a trend.
	Every chart and the table can be filtered by the <strong>medium</strong> of the post (video / image / text / other — classified from Reddit's flags plus the link itself); "All media" is always exactly the sum of the four.
</p>

<Figure
	title="Top 10 indicators over time"
	hint="The 10 most-cited individual indicators overall (by distinct comments), each tracked over time. Switch between line, stacked area, or 100% stacked to compare the mix. It effectively starts in 2025 because indicators are sampled from comments, and ~99.8% of comments are from 2025 onward — the subreddits were tiny until AI images went mainstream (r/RealOrAI near-dormant until mid-2023, r/isthisAI launched 2024)."
	caption="The ten most-cited indicators overall, each tracked over time. Click a name in the legend to inspect that indicator."
>
	{#snippet controls()}
		<MediaSelect bind:value={topMedia} />
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

<h3>Top indicators <Hint text="The most-cited individual indicators, alias-resolved so merged phrases (Curate → Merge) are combined into one canonical entry. Filter by the medium of the post to see e.g. which tells are video-specific." /></h3>
<div class="table-card">
	<div class="filter-bar table-controls">
		<label>
			Media
			<MediaSelect bind:value={tableMedia} />
		</label>
	</div>
{#if tableRows.length}
<div class="table-scroll">
	<table>
		<thead><tr><th>Indicator</th><th>Category</th><th class="num">Comments <Hint text="Distinct comments that cite this indicator (counting each comment once, summed across merged variants)." /></th></tr></thead>
		<tbody>
			{#each tableRows as row (row.indicator)}
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
<div class="table-empty">No indicators for this media type.</div>
{/if}
</div>

<Figure
	title="Mentions by category"
	hint="A mention = one comment associated with an indicator (via LLM extraction, semantic expansion, or keyword expansion). Here they're grouped into the 8 taxonomy categories."
	caption="Total mentions in each taxonomy category. A comment can contribute to several categories. Noise = phrases marked as non-indicators; toggle it in with Show noise."
>
	{#snippet controls()}
		<MediaSelect bind:value={catMedia} />
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
		<MediaSelect bind:value={otMedia} />
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
		<MediaSelect bind:value={bySubMedia} />
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
