<script lang="ts">
	import Plot from '$lib/Plot.svelte';
	import Figure from '$lib/Figure.svelte';
	import Hint from '$lib/Hint.svelte';
	import { n } from '$lib/format';
	import {
		CHART_STYLE,
		BAR_TEAL,
		SET2,
		spines,
		seriesMark,
		seriesY,
		timeGrid,
		timeTicks,
		eventMarks,
		milestoneMarks,
		type SeriesMode
	} from '$lib/chart';
	let { data } = $props();

	// Per-chart controls (all instant / client-side). Granularity re-buckets the
	// day-level series; mode switches line vs stacked area.
	let subGran = $state('week');
	let comGran = $state('week');
	let typeGran = $state('week');
	let subMode = $state<SeriesMode>('stacked');
	let comMode = $state<SeriesMode>('stacked');
	// Defaults to 100% stacked: the point of this chart is the composition shift.
	let typeMode = $state<SeriesMode>('percent');

	const toDate = (iso: string) => new Date(iso + 'T00:00:00Z');

	// Stable, sorted subreddit list + matching Set2 colours, shared by both
	// charts' colour scale and the hand-rolled legend rendered below each.
	const subs = $derived([...data.subreddits].sort());
	const subColor = $derived({ domain: subs, range: SET2.slice(0, subs.length), legend: false });

	// Bucket an ISO day to the start of its granularity bucket (UTC). Mirrors the
	// server's bucketStartSql so client re-bucketing matches the pipeline.
	function bucketStart(d: Date, gran: string): string {
		if (gran === 'month')
			return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`;
		if (gran === 'day') return d.toISOString().slice(0, 10);
		const dow = (d.getUTCDay() + 6) % 7; // Monday = 0
		const mon = new Date(d);
		mon.setUTCDate(d.getUTCDate() - dow);
		return mon.toISOString().slice(0, 10);
	}

	// Contiguous bucket axis (every bucket from the first to last day, gaps included).
	function bucketList(gran: string): string[] {
		if (!data.domain) return [];
		const out: string[] = [];
		const seen = new Set<string>();
		const d = new Date(data.domain.min + 'T00:00:00Z');
		const end = new Date(data.domain.max + 'T00:00:00Z');
		while (d <= end) {
			const b = bucketStart(d, gran);
			if (!seen.has(b)) {
				seen.add(b);
				out.push(b);
			}
			d.setUTCDate(d.getUTCDate() + 1);
		}
		return out;
	}

	// Aggregate day-level rows up to the granularity, then densify (0-fill every
	// bucket × subreddit) over the contiguous axis. Each row carries a real Date.
	function series(dayRows: { period: string; subreddit: string; count: number }[], gran: string) {
		const agg = new Map<string, number>();
		for (const r of dayRows) {
			const k = bucketStart(toDate(r.period), gran) + '|' + r.subreddit;
			agg.set(k, (agg.get(k) ?? 0) + r.count);
		}
		const dense: { period: string; date: Date; subreddit: string; count: number }[] = [];
		for (const p of bucketList(gran))
			for (const s of subs)
				dense.push({ period: p, date: toDate(p), subreddit: s, count: agg.get(p + '|' + s) ?? 0 });
		return dense;
	}

	const subData = $derived(series(data.submissionsOverTime, subGran));
	const comData = $derived(series(data.commentsOverTime, comGran));

	// Submission-type series: same densify as `series`, keyed by type instead of
	// subreddit. Types come from the data (link / text / video), stably sorted.
	const types = $derived([...new Set(data.typesOverTime.map((r) => r.type))].sort());
	const typeColor = $derived({ domain: types, range: SET2.slice(0, types.length), legend: false });
	function typeSeries(dayRows: { period: string; type: string; count: number }[], gran: string) {
		const agg = new Map<string, number>();
		for (const r of dayRows) {
			const k = bucketStart(toDate(r.period), gran) + '|' + r.type;
			agg.set(k, (agg.get(k) ?? 0) + r.count);
		}
		const dense: { period: string; date: Date; type: string; count: number }[] = [];
		for (const p of bucketList(gran))
			for (const t of types)
				dense.push({ period: p, date: toDate(p), type: t, count: agg.get(p + '|' + t) ?? 0 });
		return dense;
	}
	const typeData = $derived(typeSeries(data.typesOverTime, typeGran));
	// UTC domain for the x-scale, and event markers placed at their exact date.
	const xDomain = $derived(
		data.domain ? [toDate(data.domain.min), toDate(data.domain.max)] : undefined
	);
	const markerData = $derived(data.markers.map((m) => ({ ...m, dt: toDate(m.date) })));
	// Corpus milestones (green dotted lines) drawn on both over-time charts.
	const milestones = $derived([
		{ date: data.firstSubmission, label: 'First submission' },
		{ date: data.firstComment, label: 'First comment' }
	]);
</script>

<h2>Overview</h2>
<p class="page-desc">
	Corpus-level activity across the tracked subreddits. Read-only — counts come straight from the
	shared SQLite database.
</p>

<div class="cards">
	<div class="card"><div class="value">{n(data.counts.submissions)}</div><div class="label">Submissions <Hint text="Total posts collected across the tracked subreddits." /></div></div>
	<div class="card"><div class="value">{n(data.counts.comments)}</div><div class="label">Comments <Hint text="Total comments collected, across all submissions." /></div></div>
	<div class="card"><div class="value">{n(data.counts.uniqueSubmitters)}</div><div class="label">Unique submitters <Hint text="Distinct (non-deleted) authors who posted submissions." /></div></div>
	<div class="card"><div class="value">{n(data.counts.uniqueCommenters)}</div><div class="label">Unique commenters <Hint text="Distinct (non-deleted) authors who left comments." /></div></div>
	<div class="card"><div class="value" style="font-size:var(--text-base)">{data.range.min ?? '—'}<br />→ {data.range.max ?? '—'}</div><div class="label">Date range <Hint text="Earliest → latest submission date present in the data." /></div></div>
</div>

<Figure
	title="Submissions over time"
	hint="New submissions per time bucket, by subreddit. Pick the bucket size and line vs stacked area in the header."
	caption="Submissions per time bucket, split by subreddit. Dotted red lines mark notable AI image and video releases; labels below the axis mark the first submission and first comment collected."
>
	{#snippet controls()}
		<select bind:value={subGran} class="chart-mode" aria-label="Granularity">
			<option value="day">Day</option>
			<option value="week">Week</option>
			<option value="month">Month</option>
		</select>
		<select bind:value={subMode} class="chart-mode" aria-label="Chart mode">
			<option value="line">Line</option>
			<option value="stacked">Stacked area</option>
		</select>
	{/snippet}
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				height: 460,
				marginLeft: 55,
				marginBottom: 96,
				marginTop: 100,
				x: { type: 'utc', domain: xDomain, label: null, axis: null },
				y: seriesY(subMode, 'submissions'),
				color: subColor,
				marks: [
					...timeGrid(P, subGran),
					seriesMark(P, subData, { x: 'date', y: 'count', series: 'subreddit', mode: subMode }),
					...spines(P),
					...timeTicks(P, subGran),
					...eventMarks(P, markerData),
					...milestoneMarks(P, milestones)
				]
			})}
	/>
	<div class="chart-legend center">
		{#each subs as s, i (s)}
			<span><span class="swatch" style="background:{SET2[i % SET2.length]}"></span>{s}</span>
		{/each}
	</div>
</Figure>

<Figure
	title="Comments over time"
	hint="New comments per time bucket, by subreddit. Pick the bucket size and line vs stacked area in the header."
	caption="Comments per time bucket, split by subreddit, on the same timeline as submissions. Labels below the axis mark the first submission and first comment collected."
>
	{#snippet controls()}
		<select bind:value={comGran} class="chart-mode" aria-label="Granularity">
			<option value="day">Day</option>
			<option value="week">Week</option>
			<option value="month">Month</option>
		</select>
		<select bind:value={comMode} class="chart-mode" aria-label="Chart mode">
			<option value="line">Line</option>
			<option value="stacked">Stacked area</option>
		</select>
	{/snippet}
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				height: 460,
				marginLeft: 55,
				marginBottom: 96,
				marginTop: 100,
				x: { type: 'utc', domain: xDomain, label: null, axis: null },
				y: seriesY(comMode, 'comments'),
				color: subColor,
				marks: [
					...timeGrid(P, comGran),
					seriesMark(P, comData, { x: 'date', y: 'count', series: 'subreddit', mode: comMode }),
					...spines(P),
					...timeTicks(P, comGran),
					...eventMarks(P, markerData),
					...milestoneMarks(P, milestones)
				]
			})}
	/>
	<div class="chart-legend center">
		{#each subs as s, i (s)}
			<span><span class="swatch" style="background:{SET2[i % SET2.length]}"></span>{s}</span>
		{/each}
	</div>
</Figure>

<Figure
	title="Submission type over time"
	hint="Each type's share of submissions per time bucket (100% stacked). 'Link' is predominantly image posts (external links), 'video' is Reddit-hosted video, 'text' is a self-post. Switch to stacked area or line for absolute counts."
	caption="Submission types per time bucket. The rising share of video is the corpus-composition shift that can confound indicator trends (e.g. motion/video tells tracking the medium, not detection). Dotted red lines mark notable AI releases."
>
	{#snippet controls()}
		<select bind:value={typeGran} class="chart-mode" aria-label="Granularity">
			<option value="day">Day</option>
			<option value="week">Week</option>
			<option value="month">Month</option>
		</select>
		<select bind:value={typeMode} class="chart-mode" aria-label="Chart mode">
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
				height: 460,
				marginLeft: 55,
				marginBottom: 34,
				marginTop: 100,
				x: { type: 'utc', domain: xDomain, label: null, axis: null },
				y: seriesY(typeMode, 'submissions'),
				color: typeColor,
				marks: [
					...timeGrid(P, typeGran),
					seriesMark(P, typeData, { x: 'date', y: 'count', series: 'type', mode: typeMode }),
					...spines(P),
					...timeTicks(P, typeGran),
					...eventMarks(P, markerData)
				]
			})}
	/>
	<div class="chart-legend center">
		{#each types as t, i (t)}
			<span><span class="swatch" style="background:{SET2[i % SET2.length]}"></span>{t}</span>
		{/each}
	</div>
</Figure>

<Figure
	title="Submission type"
	hint="Posts split into video, text (self-post), or link, based on Reddit's is_video / is_self flags."
	caption="How posts break down by media type, from Reddit's is_video / is_self flags."
>
	<Plot
		render={(P, { width }) =>
			P.plot({
				width,
				style: CHART_STYLE,
				height: 150,
				marginLeft: 70,
				x: { grid: true, label: 'count' },
				y: { label: null },
				marks: [
					P.barX(data.types, { x: 'count', y: 'type', sort: { y: '-x' }, fill: BAR_TEAL, tip: true }),
					...spines(P)
				]
			})}
	/>
</Figure>
