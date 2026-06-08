<script lang="ts">
	import Plot from '$lib/Plot.svelte';
	import Hint from '$lib/Hint.svelte';
	import {
		CHART_STYLE,
		CATEGORY_SCHEME,
		BAR_TEAL,
		SET2,
		LINE_PALETTE,
		spines,
		seriesMark,
		seriesY,
		timeGrid,
		timeTicks,
		type SeriesMode
	} from '$lib/chart';

	// ── Proposed design system — demo artefact for approval (does not ship). ──

	const PALETTE = [
		{ group: 'Surfaces', items: [
			['--bg', '#f7f2e9', 'page background (warm paper)'],
			['--surface', '#fffdf8', 'cards, panels'],
			['--surface-2', '#efe7d6', 'inputs, hover'],
			['--border', '#e4dac6', 'hairlines']
		] },
		{ group: 'Ink', items: [
			['--text', '#262019', 'body text (warm ink)'],
			['--muted', '#6f675a', 'labels, captions']
		] },
		{ group: 'Accent', items: [
			['--accent', '#1f6f68', 'links, primary (deep teal)'],
			['--accent-dim', '#d8e8e5', 'active nav']
		] },
		{ group: 'Semantic', items: [
			['--good', '#2f7d55', 'success'],
			['--warn', '#b07d1a', 'warning'],
			['--danger', '#a23b2c', 'destructive']
		] }
	];

	const TYPE_SCALE = [
		['--text-3xl', '34px', 'Page / display title'],
		['--text-2xl', '28px', 'Big stat values'],
		['--text-xl', '22px', 'Section heading (h2)'],
		['--text-lg', '18px', 'Lede / sub-head'],
		['--text-md', '16px', 'Reader body, figure title'],
		['--text-base', '14px', 'App body (default)'],
		['--text-sm', '13px', 'Tables, controls'],
		['--text-xs', '12px', 'Labels, captions'],
		['--text-2xs', '11px', 'Eyebrows, pills']
	];

	const SPACING = [
		['--space-1', '4px'],
		['--space-2', '8px'],
		['--space-3', '12px'],
		['--space-4', '16px'],
		['--space-5', '24px'],
		['--space-6', '32px'],
		['--space-7', '48px']
	];

	// Sample chart data (synthetic; no DB).
	const MONTHS = [
		'2025-01-01', '2025-02-01', '2025-03-01', '2025-04-01',
		'2025-05-01', '2025-06-01', '2025-07-01', '2025-08-01'
	];
	const SERIES = ['r/RealOrAI', 'r/isthisAI'];
	const lineData = MONTHS.flatMap((d, i) =>
		SERIES.map((s, j) => ({
			date: new Date(d + 'T00:00:00Z'),
			series: s,
			count: Math.round(40 + i * (j ? 34 : 12) + (j ? 0 : 30) + Math.abs(((i * 7 + j * 13) % 11) - 5) * 6)
		}))
	);
	const barData = [
		{ indicator: 'hands / fingers', count: 5248 },
		{ indicator: 'too smooth / plastic', count: 3110 },
		{ indicator: 'garbled text', count: 2740 },
		{ indicator: 'lighting / shadows', count: 1980 },
		{ indicator: 'eyes / faces', count: 1554 },
		{ indicator: 'watermark', count: 1290 }
	];

	let mode = $state<SeriesMode>('stacked');
</script>

<div class="sg">
	<header class="sg-hero">
		<div class="eyebrow">Design system · demo artefact for approval</div>
		<h1 class="display">Uncanny Atlas</h1>
		<p class="lede">
			A small, consistent system: palette, typography, spacing, layout rules, and one standard way to
			present graphs as content. Headings use <strong>Captain Edward</strong> (<a href="https://simplebits.shop/collections/fonts">SimpleBits</a>) loaded here and on the live site; the open-source build falls back to a system serif. Body is Inter.
		</p>
	</header>

	<!-- ── Palette ───────────────────────────────────────────────────── -->
	<section>
		<h2 class="display">Palette</h2>
		<p class="note">Light theme. Charts draw from a separate qualitative ramp (ColorBrewer Set2 / Tableau).</p>
		{#each PALETTE as col (col.group)}
			<div class="swatch-group">
				<div class="swatch-group-label">{col.group}</div>
				<div class="swatches">
					{#each col.items as [token, hex, use] (token)}
						<div class="swatch">
							<div class="chip" style="background:{hex}"></div>
							<div class="swatch-meta">
								<code>{token}</code>
								<span>{hex}</span>
								<span class="muted">{use}</span>
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/each}
		<div class="swatch-group">
			<div class="swatch-group-label">Chart ramp (Set2)</div>
			<div class="ramp">
				{#each SET2 as c (c)}<span class="ramp-cell" style="background:{c}" title={c}></span>{/each}
			</div>
		</div>
	</section>

	<!-- ── Typography ────────────────────────────────────────────────── -->
	<section>
		<h2 class="display">Typography</h2>
		<div class="type-roles">
			<div class="role">
				<div class="role-name">Display — <code>--font-display</code></div>
				<div class="display sample-display">Uncanny Atlas</div>
				<p class="muted note">Wordmark + h1/h2. This is Captain Edward (SimpleBits), a licensed serif loaded here and on the live site; the open-source build falls back to a system serif.</p>
			</div>
			<div class="role">
				<div class="role-name">Body — <code>--font-sans</code></div>
				<div class="sample-body">The quick brown fox spots six fingers and a melted watermark.</div>
				<p class="muted note">Everything else. A free / system stack, committed to the repo so source builds look right.</p>
			</div>
			<div class="role">
				<div class="role-name">Links</div>
				<div class="sample-body">Inline links use a teal dotted underline — <a href="/how-it-works">how it works</a>, <a href="/runbook">run book</a> — going solid on hover.</div>
				<p class="muted note">Content / prose links. Nav items, buttons and pagers opt out (no underline).</p>
			</div>
		</div>
		<div class="type-scale">
			{#each TYPE_SCALE as [token, px, use] (token)}
				<div class="type-row">
					<span class="type-sample" style="font-size:{px}">Aa</span>
					<code>{token}</code>
					<span class="muted">{px}</span>
					<span class="muted">{use}</span>
				</div>
			{/each}
		</div>
	</section>

	<!-- ── Spacing ───────────────────────────────────────────────────── -->
	<section>
		<h2 class="display">Spacing</h2>
		<p class="note">One 4px-based scale for padding, gaps, and rhythm.</p>
		<div class="space-scale">
			{#each SPACING as [token, px] (token)}
				<div class="space-row">
					<code>{token}</code>
					<span class="space-bar" style="width:{px}"></span>
					<span class="muted">{px}</span>
				</div>
			{/each}
		</div>
	</section>

	<!-- ── Layout & content separation ───────────────────────────────── -->
	<section>
		<h2 class="display">Layout &amp; content separation</h2>
		<ul class="rules">
			<li><strong>Two containers.</strong> Long-form pages (the explainer) use a centred <em>reader column</em> (<code>--reader-width</code>, 720px). Data pages use the full-bleed <em>app shell</em> (sidebar + content up to <code>--content-max</code>).</li>
			<li><strong>Content lives in panels.</strong> Charts, forms, and static blocks sit in a <code>.panel</code> (surface + hairline border + <code>--radius</code>), separated by <code>--space-4</code>. Interactive data tables use the richer <code>.table-card</code> instead (see <em>Data tables</em>) — its controls, scroll area, empty state, and pager all live in the one box.</li>
			<li><strong>Stats use cards.</strong> Headline numbers go in a <code>.card</code> grid above the detail.</li>
			<li><strong>Sections</strong> are introduced by a display-face heading with <code>--space-6</code> above it; an optional one-line muted description sits directly under.</li>
		</ul>
		<div class="demo-cards">
			<div class="card"><div class="value">912,187</div><div class="label">Comments <Hint text="Demo stat card." /></div></div>
			<div class="card"><div class="value">5,248</div><div class="label">Top indicator</div></div>
			<div class="card"><div class="value">9</div><div class="label">Categories</div></div>
		</div>
	</section>

	<!-- ── Components ─────────────────────────────────────────────────── -->
	<section>
		<h2 class="display">Components</h2>
		<div class="panel">
			<div class="row">
				<button>Primary</button>
				<button class="ghost">Ghost</button>
				<button class="danger">Danger</button>
				<span class="pill">pill</span>
				<span class="pill" style="border-left:3px solid var(--accent)">indicator chip</span>
			</div>
			<div class="flash success" style="margin-top:12px">Success — a change was saved.</div>
			<div class="flash nudge">Nudge — something needs your attention.</div>
			<table>
				<thead><tr><th>Indicator</th><th>Category</th><th class="num">Comments</th></tr></thead>
				<tbody>
					<tr><td>six fingers</td><td><span class="pill">Anatomy</span></td><td class="num">5,248</td></tr>
					<tr><td>plastic skin</td><td><span class="pill">Style</span></td><td class="num">3,110</td></tr>
					<tr><td>garbled text</td><td><span class="pill">Text &amp; detail</span></td><td class="num">2,740</td></tr>
				</tbody>
			</table>
		</div>
	</section>

	<!-- ── Graphs as content ─────────────────────────────────────────── -->
	<section>
		<h2 class="display">Graphs as content</h2>
		<p class="note">
			One standard wrapper for every chart — a <strong>figure</strong>: a title row (with an info
			<Hint text="Hints explain what a chart shows, in one sentence." /> and optional mode toggle),
			the plot at full width, then a caption. Consistent margins, spines, grid, and the shared palette.
		</p>

		<figure class="figure">
			<div class="figure-head">
				<h3 class="figure-title">Mentions over time</h3>
				<select bind:value={mode} class="chart-mode" aria-label="Chart mode">
					<option value="line">Line</option>
					<option value="stacked">Stacked area</option>
					<option value="percent">100% stacked</option>
				</select>
			</div>
			<Plot
				render={(P, { width }) =>
					P.plot({
						width,
						style: CHART_STYLE,
						marginLeft: 55,
						marginBottom: 34,
						x: { type: 'utc', label: null, axis: null },
						y: seriesY(mode, 'mentions'),
						color: { legend: false, scheme: CATEGORY_SCHEME, domain: SERIES },
						marks: [
							...timeGrid(P, 'month'),
							seriesMark(P, lineData, { x: 'date', y: 'count', series: 'series', mode }),
							...spines(P),
							...timeTicks(P, 'month')
						]
					})}
			/>
			<div class="chart-legend center">
				{#each SERIES as s, i (s)}
					<span><span class="swatch" style="background:{SET2[i % SET2.length]}"></span>{s}</span>
				{/each}
			</div>
			<figcaption>Caption: what the reader should take away, and any caveat. Demo data.</figcaption>
		</figure>

		<figure class="figure">
			<div class="figure-head">
				<h3 class="figure-title">Top indicators</h3>
			</div>
			<Plot
				render={(P, { width }) =>
					P.plot({
						width,
						style: CHART_STYLE,
						height: 200,
						marginLeft: 130,
						x: { grid: true, label: 'comments' },
						y: { label: null },
						marks: [
							P.barX(barData, { x: 'count', y: 'indicator', sort: { y: '-x' }, fill: BAR_TEAL, tip: true }),
							...spines(P)
						]
					})}
			/>
			<figcaption>Single-series bars use one fill from the ramp; ranked, with a left axis of labels.</figcaption>
		</figure>

		<div class="ramp" style="margin-top:8px">
			{#each LINE_PALETTE.slice(0, 10) as c (c)}<span class="ramp-cell" style="background:{c}" title={c}></span>{/each}
		</div>
		<p class="note">Multi-series line charts cycle the Tableau ramp (above); a clickable legend sits below the plot.</p>
	</section>

	<!-- ── Data tables ───────────────────────────────────────────────── -->
	<section>
		<h2 class="display">Data tables</h2>
		<p class="note">
			Interactive lists (indicators, semantic matches, merges) use a <strong>table card</strong>: one
			bordered box that holds its own controls, the scrollable table, an empty state, and a pagination
			footer — so the filters never float loose above the data. Static reference tables (the run book)
			stay in a plain <code>.panel</code>.
		</p>

		<div class="table-card">
			<form class="filter-bar table-controls" onsubmit={(e) => e.preventDefault()}>
				<label>
					<span>Search <Hint text="Controls live inside the card, divided from the table by a hairline." /></span>
					<input type="search" placeholder="phrase…" />
				</label>
				<label>
					Category
					<select><option>All</option><option>Anatomy</option><option>Style</option></select>
				</label>
				<label>
					Sort
					<select><option>Frequency ↓</option><option>Length ↓</option></select>
				</label>
			</form>
			<div class="table-scroll">
				<table>
					<thead><tr><th>Indicator</th><th>Category</th><th class="num">Comments</th></tr></thead>
					<tbody>
						<tr><td>six fingers</td><td><span class="pill">Anatomy</span></td><td class="num">5,248</td></tr>
						<tr><td>plastic skin</td><td><span class="pill">Style</span></td><td class="num">3,110</td></tr>
						<tr><td>garbled text</td><td><span class="pill">Text &amp; detail</span></td><td class="num">2,740</td></tr>
					</tbody>
				</table>
			</div>
			<div class="table-foot">
				<span>1–3 of 128</span>
				<span class="pager"><span class="muted">← Prev</span><a href="#top">Next →</a></span>
			</div>
		</div>

		<p class="note" style="margin-top:var(--space-5)">
			When the filters match nothing, the table is replaced by a centred empty state — never a blank
			box or a lone header row. The pager is hidden when everything fits on one page.
		</p>
		<div class="table-card">
			<form class="filter-bar table-controls" onsubmit={(e) => e.preventDefault()}>
				<label>
					<span>Search</span>
					<input type="search" value="zzzz" />
				</label>
			</form>
			<div class="table-empty">No indicators match these filters. Try a different Mode, or clear the search.</div>
		</div>
	</section>
</div>

<style>
	.sg {
		max-width: var(--content-max);
		padding: var(--space-5) var(--space-6) var(--space-7);
	}
	.display {
		font-family: var(--font-display);
		font-weight: 800;
		letter-spacing: -0.01em;
	}
	.sg-hero {
		margin-bottom: var(--space-7);
	}
	.eyebrow {
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-size: var(--text-2xs);
		color: var(--muted);
		margin-bottom: var(--space-2);
	}
	.sg-hero h1 {
		font-size: var(--text-3xl);
		margin: 0 0 var(--space-3);
		line-height: 1.05;
	}
	.lede {
		font-size: var(--text-md);
		color: var(--text);
		max-width: var(--reader-width);
		line-height: 1.6;
		margin: 0;
	}
	section {
		margin-top: var(--space-7);
		border-top: 1px solid var(--border);
		padding-top: var(--space-5);
	}
	section > h2 {
		font-size: var(--text-xl);
		margin: 0 0 var(--space-2);
	}
	.note {
		color: var(--muted);
		font-size: var(--text-sm);
		max-width: var(--reader-width);
		margin: 0 0 var(--space-4);
	}
	.muted {
		color: var(--muted);
	}
	code {
		font-family: var(--font-mono);
		font-size: 0.85em;
		background: var(--surface-2);
		padding: 1px 5px;
		border-radius: 5px;
	}

	/* Palette */
	.swatch-group {
		margin-bottom: var(--space-4);
	}
	.swatch-group-label {
		font-size: var(--text-2xs);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
		margin-bottom: var(--space-2);
	}
	.swatches {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
		gap: var(--space-3);
	}
	.swatch {
		display: flex;
		gap: var(--space-3);
		align-items: center;
	}
	.chip {
		width: 40px;
		height: 40px;
		border-radius: var(--radius-sm);
		border: 1px solid var(--border);
		flex: none;
	}
	.swatch-meta {
		display: flex;
		flex-direction: column;
		gap: 1px;
		font-size: var(--text-xs);
	}
	.ramp {
		display: flex;
		border-radius: var(--radius-sm);
		overflow: hidden;
		width: fit-content;
		border: 1px solid var(--border);
	}
	.ramp-cell {
		width: 30px;
		height: 24px;
	}

	/* Typography */
	.type-roles {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: var(--space-4);
		margin-bottom: var(--space-5);
	}
	.role {
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: var(--space-4);
	}
	.role-name {
		font-size: var(--text-xs);
		color: var(--muted);
		margin-bottom: var(--space-2);
	}
	.sample-display {
		font-size: var(--text-2xl);
		line-height: 1.1;
	}
	.sample-body {
		font-size: var(--text-md);
		line-height: 1.5;
	}
	.type-scale {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.type-row {
		display: grid;
		grid-template-columns: 60px 120px 60px 1fr;
		align-items: baseline;
		gap: var(--space-3);
		padding-bottom: var(--space-2);
		border-bottom: 1px solid var(--border);
	}
	.type-sample {
		font-weight: 600;
		line-height: 1;
	}

	/* Spacing */
	.space-scale {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.space-row {
		display: grid;
		grid-template-columns: 90px 1fr 50px;
		align-items: center;
		gap: var(--space-3);
	}
	.space-bar {
		height: 16px;
		background: var(--accent);
		border-radius: 3px;
	}

	/* Layout rules */
	.rules {
		max-width: var(--reader-width);
		font-size: var(--text-sm);
		line-height: 1.6;
		color: var(--text);
		padding-left: var(--space-4);
	}
	.rules li {
		margin-bottom: var(--space-2);
	}
	.demo-cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: var(--space-3);
		margin-top: var(--space-4);
		max-width: 520px;
	}

	/* Components */
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		align-items: center;
	}

	/* .figure / .figure-head / .figure-title / figcaption are now global
	   (app.css), shared with the real charts via Figure.svelte. */
</style>
