<script lang="ts">
	import { n } from '$lib/format';
	let { data } = $props();

	// ---------------------------------------------------------------------------
	// §1  "Do these share words?" - keyword matching fails on paraphrase
	// ---------------------------------------------------------------------------
	const PAIRS = [
		['the hands look melty', 'weird fused fingers'],
		['shadow points the wrong way', 'the lighting makes no sense'],
		['the text is gibberish', 'warped nonsense writing']
	];
	let pairIdx = $state(0);
	const pair = $derived(PAIRS[pairIdx]);
	const STOP = new Set(['the', 'a', 'is', 'are', 'look', 'looks', 'makes', 'no', 'way']);
	const tok = (s: string) => s.toLowerCase().split(/\s+/);
	const shared = $derived.by(() => {
		const [a, b] = pair;
		const sa = new Set(tok(a).filter((w) => !STOP.has(w)));
		return new Set(tok(b).filter((w) => !STOP.has(w) && sa.has(w)));
	});

	// ---------------------------------------------------------------------------
	// §3/§4  The meaning map - embeddings, similarity, expansion
	// ---------------------------------------------------------------------------
	type Dot = { phrase: string; x: number; y: number; color: string; cue: boolean };
	const CLUSTERS = [
		{
			color: '#1f6f68',
			cx: 24,
			cy: 24,
			cue: 'hands',
			members: [
				['six fingers', -9, 6],
				['mangled hands', 8, -7],
				['extra finger', -7, -8],
				['fused fingers', 10, 5],
				['weird fingers', 2, 10],
				['too many knuckles', -11, -1]
			]
		},
		{
			color: '#59a14f',
			cx: 75,
			cy: 22,
			cue: 'shadows',
			members: [
				['wrong shadow', -9, 7],
				['no shadow at all', 9, -6],
				['light from nowhere', -9, -6],
				['inconsistent shadows', 8, 7],
				['shadow points wrong', -1, 11]
			]
		},
		{
			color: '#b07aa1',
			cx: 20,
			cy: 53,
			cue: 'garbled text',
			members: [
				['gibberish letters', -9, -7],
				['the sign is nonsense', 10, 5],
				['warped writing', -10, 6],
				['melted text', 7, -8],
				['words make no sense', 1, 10]
			]
		},
		{
			color: '#e15759',
			cx: 79,
			cy: 55,
			cue: 'eyes look off',
			members: [
				['dead eyes', -9, 7],
				['the face is melting', 9, -6],
				['wonky teeth', -10, -6],
				['mismatched ears', 8, 7],
				['plastic stare', -1, 11]
			]
		},
		{
			color: '#76b7b2',
			cx: 29,
			cy: 81,
			cue: 'too smooth',
			members: [
				['plastic skin', -9, -6],
				['that AI sheen', 9, 5],
				['airbrushed look', -10, 5],
				['uncanny', 7, -7]
			]
		},
		{
			color: '#bab0ac',
			cx: 79,
			cy: 83,
			cue: null,
			members: [
				['cute dog!', -8, -6],
				['where is this?', 9, 4],
				['first lol', -9, 6],
				['saved, thanks', 7, -7],
				['this is so sad', 0, 10]
			]
		}
	];
	const DOTS: Dot[] = [];
	const CUES: Dot[] = [];
	for (const c of CLUSTERS) {
		if (c.cue) {
			const cueDot = { phrase: c.cue, x: c.cx, y: c.cy, color: c.color, cue: true };
			DOTS.push(cueDot);
			CUES.push(cueDot);
		}
		for (const [phrase, dx, dy] of c.members)
			DOTS.push({ phrase: phrase as string, x: c.cx + (dx as number), y: c.cy + (dy as number), color: c.color, cue: false });
	}

	let probe = $state({ x: 24, y: 24 });
	let threshold = $state(0.73);
	let mode = $state<'probe' | 'expand'>('probe');
	let hovered = $state<Dot | null>(null);
	let dragging = false;
	let svgEl: SVGSVGElement | undefined = $state();

	const radius = $derived((1 - threshold) * 85);
	const d2 = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);
	const caught = $derived(DOTS.filter((d) => !d.cue && d2(d, probe) <= radius));
	const tagged = $derived.by(() => {
		const s = new Set<Dot>();
		for (const indicator of CUES) for (const d of DOTS) if (!d.cue && d2(d, indicator) <= radius) s.add(d);
		return s;
	});
	const isLit = (d: Dot) => (mode === 'probe' ? caught.includes(d) : d.cue || tagged.has(d));

	function toPoint(e: PointerEvent) {
		const r = svgEl!.getBoundingClientRect();
		return {
			x: Math.max(2, Math.min(98, ((e.clientX - r.left) / r.width) * 100)),
			y: Math.max(2, Math.min(98, ((e.clientY - r.top) / r.height) * 100))
		};
	}
	function onDown(e: PointerEvent) {
		if (mode !== 'probe') return;
		dragging = true;
		probe = toPoint(e);
		svgEl!.setPointerCapture(e.pointerId);
	}
	function onMove(e: PointerEvent) {
		if (dragging) probe = toPoint(e);
	}
	function onUp() {
		dragging = false;
	}

	// ---------------------------------------------------------------------------
	// §4 (seeds)  Which ◆ indicators are active - only a seeded indicator reaches out
	// ---------------------------------------------------------------------------
	const SEED_R = 17;
	let seeded = $state(new Set(CUES.map((c) => c.phrase)));
	function toggleSeed(cue: string) {
		const s = new Set(seeded);
		if (s.has(cue)) s.delete(cue);
		else s.add(cue);
		seeded = s;
	}
	const seedLit = $derived.by(() => {
		const s = new Set<Dot>();
		for (const c of CUES)
			if (seeded.has(c.phrase)) for (const d of DOTS) if (!d.cue && d2(d, c) <= SEED_R) s.add(d);
		return s;
	});

	// ---------------------------------------------------------------------------
	// §5  Live coverage bar (uses the real, currently-filling numbers)
	// ---------------------------------------------------------------------------
	const coveragePct = $derived(data.totalComments ? (data.embedded / data.totalComments) * 100 : 0);
	const sampleSize = $derived(data.llmSample || 8000);
	const samplePct = $derived(data.totalComments ? Math.max(0.4, (sampleSize / data.totalComments) * 100) : 1);

	// ---------------------------------------------------------------------------
	// §6  Merge - scattered synonyms collapse into one canonical indicator
	// ---------------------------------------------------------------------------
	const SYN = [
		{ p: 'wrong hands', x: 16, y: 28 },
		{ p: 'funny hands', x: 80, y: 20 },
		{ p: 'hands messed up', x: 26, y: 80 },
		{ p: 'six fingers', x: 84, y: 72 },
		{ p: 'mangled fingers', x: 58, y: 46 }
	];
	const CANON = { x: 50, y: 50 };
	let merged = $state(false);
</script>

<div class="reader">
	<h1>How Uncanny Atlas works</h1>
	<p class="lede">
		It is difficult to know what is 'real' and what is generated by AI on the internet. People generally point to specific things when declaring <em>“that's AI”</em> - The hands, the
		light, a plastic sheen they can't quite name. On
		<a href="https://reddit.com/r/isthisAI">r/isthisAI</a> and
		<a href="https://reddit.com/r/RealOrAI">r/RealOrAI</a>, thousands of people argue about exactly
		that, in the comments.<br/><br/>This tool is an attempt to turn that pile of arguments - currently
		<strong>{n(data.totalComments)}</strong> comments - into a map of the <em>indicators people actually
		use</em>. This page explains how, from first principles. No prior knowledge of the project is assumed;
		just scroll, and play with the figures.
	</p>

	<p>
		The whole job sounds simple: <em>find every comment that names an indicator, work out which indicator, and
		count them.</em> The trouble is hiding in the middle. Let's build up to it.
	</p>

	<h2 id="problem">1 · A thousand ways to say one thing</h2>
	<p>
		People don't speak in tidy labels. The single idea “the hands are wrong” shows up as <span class="chip" style="border-color:#1f6f68">six fingers</span>
		<span class="chip" style="border-color:#1f6f68">melty hands</span>
		<span class="chip" style="border-color:#1f6f68">too many knuckles</span>
		<span class="chip" style="border-color:#1f6f68">fused fingers</span> - and a hundred more.
	</p>
	<p>
		The obvious approach is to search for matching <em>words</em>. But meaning and words come apart
		fast. Here are two comments that plainly mean the same thing. Which words do they actually share?
	</p>

	<figure class="fig">
		<div class="kw">
			{#each pair as phrase, i (i)}
				<div class="kw-row">
					{#each tok(phrase) as w (w)}
						<span class="kw-word" class:match={shared.has(w)}>{w}</span>
					{/each}
				</div>
				{#if i === 0}<div class="kw-vs">means the same as ↓</div>{/if}
			{/each}
			<div class="kw-out">
				Shared meaningful words: <strong>{shared.size}</strong>
				{shared.size === 0 ? '- keyword matching finds nothing in common.' : ''}
			</div>
		</div>
		<button class="btn" onclick={() => (pairIdx = (pairIdx + 1) % PAIRS.length)}>Try another pair</button>
		<figcaption>
			Two paraphrases of the same indicator, broken into words. Highlighted = shared. Almost always there's
			no overlap - so counting words would split one indicator into dozens, or miss it entirely.
		</figcaption>
	</figure>

	<p>We need a way for the computer to see <em>meaning</em>, not spelling.</p>

	<h2 id="extraction">2 · A model that pulls out the indicators</h2>
	<p>
		First, someone (or something) has to read a comment and say what indicator it names. This project used a small language model
		(<code>gemma3:4b</code>, running locally). It read one comment and returned the indicators as short
		phrases:
	</p>
	<figure class="fig">
		<div class="extract">
			<div class="comment">“lol no way this is real, look at her <u>hands</u> - she's got like <u>six fingers</u> and the <u>shadows</u> are all over the place”</div>
			<div class="arrow">extracts →</div>
			<div class="cues">
				<span class="chip" style="border-color:#1f6f68">six fingers</span>
				<span class="chip" style="border-color:#59a14f">wrong shadows</span>
			</div>
		</div>
		<figcaption>The model reads the text and lists the visual indicators it cited.</figcaption>
	</figure>
	<p>
		This works, but it has two limits. It's <strong>slow and costly</strong> - one comment per call -
		so the project only runs on a <em>sample</em> of a few thousand.
	</p>
	<p>
		<strong>How we choose that sample matters.</strong> We don't read random comments - only ones
		likely to be discussing authenticity at all, picked by a deliberately broad keyword net:
		<span class="chip">AI</span> <span class="chip">real</span> <span class="chip">fake</span>
		<span class="chip">generated</span> <span class="chip">obvious</span> <span class="chip">look</span>.
		These are <em>topical</em> words on purpose - not visual-indicator words. Filtering the sample for visual-indicator words (finger, shadow, lighting) would be circular: you cannot discover which indicators people use if you only read comments that already mention the indicators you guessed. So the net catches “is this real or AI?” talk, and lets the <em>model</em>
		find whatever indicator is actually there (and occasionally a couple that aren't).
	</p>
	<p>
		So after this step we have a few thousand comments, each with real indicator-phrases - but those
		phrases are still just <em>words</em>, with the paraphrase problem from §1. Time to fix meaning.
	</p>

	<h2 id="embeddings">3 · Turning meaning into a place on a map</h2>
	<p>
		Here's the key trick. Imagine a giant map where every phrase gets an <strong>address</strong>, and
		phrases that <em>mean</em> similar things live close together - same street - while unrelated ones
		live in different cities. That address (a long list of numbers; really 768 of them) is called an
		<strong>embedding</strong>. A second little AI - an embedding model
		(<code>nomic-embed-text</code>, also running locally) - learned to place text on this map by
		reading a mountain of writing.
	</p>
	<p>
		Below is a flattened, 2-D sketch of such a map for some real comment-phrases. Notice the clumps:
		all the hand complaints sit together, all the shadow ones together - <em>even though they share no
		words.</em> The big <span class="cue-key">◆</span> markers are our known indicators; the small dots are
		individual comments.
	</p>
	<p>
		<strong>Drag the crosshair</strong> anywhere (or hit a button to jump it to an indicator). Everything
		inside the circle is “close enough to count as the same thing.” Drag the slider to change how close
		<em>close</em> has to be.
	</p>

	<figure class="fig">
		<div class="mapwrap">
			<svg
				bind:this={svgEl}
				viewBox="0 0 100 100"
				class="map"
				class:grab={mode === 'probe'}
				onpointerdown={onDown}
				onpointermove={onMove}
				onpointerup={onUp}
				role="presentation"
			>
				<rect x="0.5" y="0.5" width="99" height="99" class="frame" />

				{#if mode === 'probe'}
					<circle cx={probe.x} cy={probe.y} r={radius} class="range" />
					{#each caught as d (d.phrase)}
						<line x1={probe.x} y1={probe.y} x2={d.x} y2={d.y} class="link" />
					{/each}
				{:else}
					{#each CUES as c (c.phrase)}
						<circle cx={c.x} cy={c.y} r={radius} class="range soft" />
					{/each}
				{/if}

				{#each DOTS as d (d.phrase)}
					{#if d.cue}
						<g
							class="cue"
							class:lit={isLit(d)}
							onpointerenter={() => (hovered = d)}
							onpointerleave={() => (hovered = null)}
							role="presentation"
						>
							<rect x={d.x - 2.2} y={d.y - 2.2} width="4.4" height="4.4" transform={`rotate(45 ${d.x} ${d.y})`} fill={d.color} />
						</g>
					{:else}
						<circle
							cx={d.x}
							cy={d.y}
							r="1.7"
							fill={d.color}
							class="dot"
							class:lit={isLit(d)}
							onpointerenter={() => (hovered = d)}
							onpointerleave={() => (hovered = null)}
							role="presentation"
						/>
					{/if}
				{/each}

				{#if mode === 'probe'}
					<g class="probe">
						<circle cx={probe.x} cy={probe.y} r="2.6" />
						<line x1={probe.x - 4} y1={probe.y} x2={probe.x + 4} y2={probe.y} />
						<line x1={probe.x} y1={probe.y - 4} x2={probe.x} y2={probe.y + 4} />
					</g>
				{/if}

				{#if hovered}
					<text x={hovered.x} y={hovered.y - 3.5} class="tip" text-anchor="middle">{hovered.phrase}</text>
				{/if}
			</svg>
		</div>

		<div class="controls">
			<div class="seg">
				<button class:on={mode === 'probe'} onclick={() => (mode = 'probe')}>Probe a point</button>
				<button class:on={mode === 'expand'} onclick={() => (mode = 'expand')}>Tag near every indicator</button>
			</div>
			{#if mode === 'probe'}
				<div class="snaps">
					jump to:
					{#each CLUSTERS.filter((c) => c.cue) as c (c.cue)}
						<button class="snap" style="--c:{c.color}" onclick={() => (probe = { x: c.cx, y: c.cy })}>{c.cue}</button>
					{/each}
				</div>
			{/if}
			<label class="slider">
				Match threshold: <strong>{threshold.toFixed(2)}</strong>
				<input type="range" min="0.55" max="0.9" step="0.01" bind:value={threshold} />
				<span class="muted">{threshold > 0.8 ? 'strict (few, precise)' : threshold < 0.65 ? 'loose (many, some wrong)' : 'balanced'}</span>
			</label>
		</div>

		<figcaption>
			{#if mode === 'probe'}
				<strong>{caught.length}</strong> comment{caught.length === 1 ? '' : 's'} are within range of the
				crosshair right now{#if caught.length}: {#each caught.slice(0, 8) as d (d.phrase)}<span class="chip sm" style="border-color:{d.color}">{d.phrase}</span>{/each}{/if}. Park
				it on an indicator and watch it gather that indicator's paraphrases.
			{:else}
				Each ◆ indicator grabs the comments near it: <strong>{tagged.size}</strong> tagged. Notice the
				grey “not an indicator” cluster - real reactions like <em>“cute dog!”</em> - sits far from every indicator,
				so it's correctly left alone.
			{/if}
		</figcaption>
	</figure>

	<p>
		To check if two phrases mean the same thing, the computer just measures the <strong>distance
		between their addresses</strong>. Close = same idea. That distance threshold is the
		<code>0.73</code> you saw on the slider. Crank it up and you demand near-identical meaning (you
		miss loose paraphrases); loosen it and you sweep in more, including the occasional wrong one.
	</p>

	<h2 id="expansion">4 · Letting the indicators find their own comments</h2>
	<p>
		Now the payoff. The first model only saw a sample. But <em>every</em> comment can be placed on the map cheaply. So for each known indicator (the ◆ markers), we simply ask: <em>which comment-dots are
		nearby?</em> - and tag them all, no re-reading required. Flip the figure above to
		<strong>“Tag near every indicator.”</strong>
	</p>
	<p>
		This is <strong>semantic expansion</strong>. A comment that says <em>“her fingers are all fused
		together”</em> never typed the word “hands,” but it lives right next door to the
		<span class="cue-key">◆</span> hands indicator - so it gets counted. That's how a tiny sample grows into
		broad coverage, and why the counts reflect what people <em>actually said</em> rather than just the
		few comments the model had time for.
	</p>
	<p>
		One guard rail: expansion only looks at comments long enough to be <em>describing</em> something - at
		least 20 characters, and not a bot. A lone <span class="chip">👍</span> or
		<span class="chip">lol</span> sits near plenty of indicators on the map but isn't evidence of anything,
		so it's skipped. Without that floor a vague seed like “AI voice” would hoover up thousands of one-word
		reactions and drown out the real signal.
	</p>

	<h3 id="seeds">Where the ◆ indicators come from: seeds</h3>
	<p>
		Those ◆ markers have a name: <strong>seeds</strong>. A seed is a known indicator that semantic
		expansion reaches out <em>from</em> - each one gathers the comment-dots in its neighbourhood. Seeds
		aren't hand-listed up front: the pipeline builds them automatically by taking the ~200
		most-frequently extracted phrases and sorting each into a category - that's the
		<strong>taxonomy</strong>. A curator (me, in this case) can also seed a phrase the model never surfaced, or un-seed a
		bad one. Toggle the seeds below and watch coverage shrink and grow - the grey
		non-indicator cluster is never seeded, so it stays dark:
	</p>
	<figure class="fig">
		<div class="mapwrap small">
			<svg viewBox="0 0 100 100" class="map">
				<rect x="0.5" y="0.5" width="99" height="99" class="frame" />
				{#each CUES as c (c.phrase)}
					{#if seeded.has(c.phrase)}<circle cx={c.x} cy={c.y} r={SEED_R} class="range soft" />{/if}
				{/each}
				{#each DOTS as d (d.phrase)}
					{#if d.cue}
						<rect
							x={d.x - 2.2}
							y={d.y - 2.2}
							width="4.4"
							height="4.4"
							transform={`rotate(45 ${d.x} ${d.y})`}
							fill={seeded.has(d.phrase) ? d.color : 'none'}
							stroke={d.color}
							stroke-width="0.6"
						/>
					{:else}
						<circle cx={d.x} cy={d.y} r="1.7" fill={d.color} class="dot" class:lit={seedLit.has(d)} />
					{/if}
				{/each}
			</svg>
		</div>
		<div class="snaps">
			seeds:
			{#each CUES as c (c.phrase)}
				<button
					class="snap"
					class:off={!seeded.has(c.phrase)}
					style="--c:{c.color}"
					onclick={() => toggleSeed(c.phrase)}>{seeded.has(c.phrase) ? '●' : '○'} {c.phrase}</button>
			{/each}
		</div>
		<figcaption>
			<strong>{seedLit.size}</strong> comment{seedLit.size === 1 ? '' : 's'} gathered. Only
			<strong>seeded</strong> ◆ indicators (filled) reach out; an un-seeded one (hollow) goes dark, and
			so does its neighbourhood. More seeds → more coverage - which is why the taxonomy, and the curator's
			seed edits, decide how much the map can see. (We'll tidy these scattered phrasings into
			<a href="#merging">merged groups</a> next.)
		</figcaption>
	</figure>

	<h2 id="coverage">5 · From a teaspoon to the whole ocean</h2>
	<p>
		The scale gap is what makes this worthwhile. Reading a comment with the language model is slow, so
		only about <strong>{n(sampleSize)}</strong> were ever read that way. Placing a comment on the map
		is cheap, so <em>every</em> comment can get an address - all
		<strong>{n(data.totalComments)}</strong> of them. The bar shows how much of the corpus is mapped:
	</p>
	<figure class="fig">
		<div class="bar">
			<div class="bar-fill" style="width:{coveragePct.toFixed(2)}%"></div>
			<div class="bar-tick" style="left:{samplePct}%" title="the language-model sample"></div>
		</div>
		<div class="bar-legend">
			<span><span class="sw fill"></span> mapped: {n(data.embedded)} / {n(data.totalComments)} ({coveragePct.toFixed(1)}%)</span>
			<span><span class="sw tick"></span> read by the language model: ≈{n(sampleSize)} (the thin mark)</span>
		</div>
		<figcaption>
			The thin mark is the sliver a human-speed reader could cover; the fill is what cheap embeddings
			reach. Because every comment has a map address, semantic expansion can draw on the whole corpus
			instead of just the sample.
		</figcaption>
	</figure>

	<h2 id="cleanup">6 · Tidying the map</h2>
	<p>Two messes remain, and both are human-in-the-loop.</p>

	<h3 id="merging">Merging synonyms into one canonical group</h3>
	<p>
		First, the <em>same</em> indicator is scattered across synonyms, so its count is split several ways. We
		<strong>merge</strong> the variants into one <strong>canonical</strong> indicator and re-point every
		comment to it. They collapse into a single entry everywhere on the Explore side -
		<a href="/explore/indicators">Top indicators</a>, <a href="/explore/lookup">Inspect</a>, and Semantic
		matches - and their counts combine, so the tally reflects the real concept instead of splitting across
		spellings. (Each raw phrase is still curated on its own - and a merged group is itself just a tidied
		<a href="#seeds">seed</a>.) Merging is done on the <a href="/curate/merge">Merge page</a>. Press the
		button:
	</p>
	<figure class="fig">
		<div class="mapwrap small">
			<svg viewBox="0 0 100 100" class="map">
				<rect x="0.5" y="0.5" width="99" height="99" class="frame" />
				{#if merged}
					{#each SYN as sdot (sdot.p)}
						<line x1={CANON.x} y1={CANON.y} x2={CANON.x} y2={CANON.y} class="link" />
					{/each}
				{/if}
				{#each SYN as sdot (sdot.p)}
					<circle
						cx={merged ? CANON.x : sdot.x}
						cy={merged ? CANON.y : sdot.y}
						r="2"
						fill="#1f6f68"
						class="syn"
					/>
				{/each}
				{#each SYN as sdot (sdot.p)}
					<text
						x={sdot.x}
						y={sdot.y + 4.8}
						class="tip synlabel"
						class:hide={merged}
						text-anchor={sdot.x < 22 ? 'start' : sdot.x > 78 ? 'end' : 'middle'}>{sdot.p}</text>
				{/each}
				{#if merged}
					<rect x={CANON.x - 2.6} y={CANON.y - 2.6} width="5.2" height="5.2" transform={`rotate(45 ${CANON.x} ${CANON.y})`} fill="#1f6f68" />
					<text x={CANON.x} y={CANON.y - 5} class="tip" text-anchor="middle">hands</text>
				{/if}
			</svg>
		</div>
		<button class="btn" onclick={() => (merged = !merged)}>{merged ? 'Un-merge' : 'Merge into “hands”'}</button>
		<figcaption>
			Five scattered phrasings - <em>wrong hands, six fingers, mangled fingers…</em> - collapse into a
			single canonical indicator. Now the count reflects the real concept instead of splitting across
			spellings.
		</figcaption>
	</figure>
	<p>
		Second, the model looking for indicators sometimes builds a <em>fake</em> indicator - a vague verdict like “looks obviously
		fake,” which isn't a visual indicator at all. Left on the map, semantic expansion would drag hundreds of
		reaction comments to it. So a curator (again, in this case me) marks it <strong>Noise</strong> - the equivalent of pulling
		that house off the map. Expansion then skips it forever, and (because the decision is written into
		the master map) it stays gone even after future runs. That grey “not an indicator” blob in the big figure
		is exactly what Noise looks like: present, but never matched against comments.
	</p>

	<h2>What you end up with</h2>
	<p>
		Put it together - read a sample, place everything on the map of meaning, let indicators gather their own
		comments, then manually merge and de-noise - and the pile of {n(data.totalComments)} arguments becomes a
		perspective on <em>which indicators people actually rely on.</em><br/><br/>
		{#if data.top}In this dataset, from my perspective, the most-cited indicator is <span class="chip" style="border-color:#1f6f68">{data.top.indicator}</span> with
		<strong>{n(data.top.count)}</strong> associated comments.{/if}
	</p>
	<div class="cta">
		<a class="cta-btn primary" href="/explore/indicators">See the live results →</a>
		<a class="cta-btn" href="/explore/lookup">Inspect a single indicator →</a>
		<a class="cta-btn" href="/runbook">Run it yourself (Run book) →</a>
	</div>
</div>

<style>
	.reader {
		max-width: 720px;
		margin: 0 auto;
		font-size: 16px;
		line-height: 1.7;
	}
	.reader h1 {
		font-size: 34px;
		line-height: 1.1;
		margin: 4px 0 16px;
	}
	.reader h2 {
		font-size: 22px;
		margin: 44px 0 6px;
		scroll-margin-top: 16px;
	}
	.reader p {
		margin: 12px 0;
		color: var(--text);
	}
	.lede {
		font-size: 18px;
		color: var(--text);
	}
	.chip {
		display: inline-block;
		padding: 1px 8px;
		margin: 2px 2px;
		border: 1px solid var(--border);
		border-left-width: 3px;
		border-radius: 6px;
		font-size: 13px;
		background: var(--surface);
		white-space: nowrap;
	}
	.chip.sm {
		font-size: 11px;
		padding: 0 6px;
	}
	.cue-key {
		color: #1f6f68;
		font-weight: 700;
	}

	.fig {
		margin: 22px 0;
		padding: 16px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}
	figcaption {
		font-size: 13px;
		color: var(--muted);
		margin-top: 12px;
		line-height: 1.5;
	}
	.btn {
		margin-top: 12px;
	}

	/* keyword widget */
	.kw-row {
		display: flex;
		flex-wrap: wrap;
		gap: 5px;
		margin: 4px 0;
	}
	.kw-word {
		padding: 2px 8px;
		border-radius: 6px;
		background: var(--surface-2);
		font-size: 14px;
	}
	.kw-word.match {
		background: #fde68a;
		color: #7c4a02;
	}
	.kw-vs {
		color: var(--muted);
		font-size: 12px;
		margin: 6px 0;
	}
	.kw-out {
		margin-top: 12px;
		font-size: 14px;
		color: var(--text);
	}

	/* extraction */
	.extract {
		display: grid;
		grid-template-columns: 1fr auto auto;
		align-items: center;
		gap: 14px;
	}
	.comment {
		background: var(--surface-2);
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 14px;
	}
	.comment u {
		text-decoration-color: var(--accent);
	}
	.arrow {
		color: var(--muted);
		font-size: 12px;
		white-space: nowrap;
	}
	.cues {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	/* meaning map */
	.mapwrap {
		max-width: 480px;
		margin: 0 auto;
	}
	.mapwrap.small {
		max-width: 320px;
	}
	.map {
		width: 100%;
		aspect-ratio: 1;
		display: block;
		touch-action: none;
	}
	.map.grab {
		cursor: crosshair;
	}
	.frame {
		fill: var(--surface);
		stroke: var(--border);
		stroke-width: 0.4;
	}
	.dot {
		opacity: 0.32;
		transition: opacity 0.12s;
	}
	.dot.lit {
		opacity: 1;
	}
	.cue rect {
		opacity: 0.5;
		transition: opacity 0.12s;
	}
	.cue.lit rect {
		opacity: 1;
	}
	.range {
		fill: rgba(31, 111, 104, 0.1);
		stroke: var(--accent);
		stroke-width: 0.4;
		stroke-dasharray: 1.5 1.2;
	}
	.range.soft {
		fill: rgba(110, 168, 254, 0.06);
		stroke-opacity: 0.5;
	}
	.link {
		stroke: var(--accent);
		stroke-width: 0.3;
		opacity: 0.4;
	}
	.syn {
		transition:
			cx 0.6s cubic-bezier(0.5, 0, 0.2, 1),
			cy 0.6s cubic-bezier(0.5, 0, 0.2, 1);
	}
	.probe circle {
		fill: none;
		stroke: var(--text);
		stroke-width: 0.6;
	}
	.probe line {
		stroke: var(--text);
		stroke-width: 0.5;
	}
	.tip {
		font-size: 3.2px;
		fill: var(--text);
		paint-order: stroke;
		stroke: #fff;
		stroke-width: 0.9;
	}
	.synlabel {
		fill: var(--muted);
		transition: opacity 0.25s;
	}
	.synlabel.hide {
		opacity: 0;
	}

	.controls {
		margin-top: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.seg {
		display: inline-flex;
		gap: 0;
		border: 1px solid var(--border);
		border-radius: 8px;
		overflow: hidden;
		width: fit-content;
	}
	.seg button {
		background: var(--surface);
		color: var(--text);
		border: none;
		border-radius: 0;
		padding: 6px 12px;
	}
	.seg button.on {
		background: var(--accent);
		color: #fff;
	}
	.snaps {
		font-size: 12px;
		color: var(--muted);
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		align-items: center;
	}
	.snap {
		background: var(--surface);
		color: var(--text);
		border: 1px solid var(--border);
		border-left: 3px solid var(--c);
		padding: 3px 8px;
		font-size: 12px;
	}
	/* Un-seeded toggle in the seeds figure: dimmed, hollow. */
	.snap.off {
		color: var(--muted);
		border-left-color: var(--border);
		background: var(--surface-2);
	}
	.slider {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		flex-wrap: wrap;
	}
	.slider input {
		flex: 1;
		min-width: 160px;
		accent-color: var(--accent);
	}
	.muted {
		color: var(--muted);
		font-size: 12px;
	}

	/* coverage bar */
	.bar {
		position: relative;
		height: 26px;
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: 8px;
		overflow: hidden;
	}
	.bar-fill {
		height: 100%;
		background: linear-gradient(90deg, #76b7b2, #1f6f68);
		transition: width 0.4s;
	}
	.bar-tick {
		position: absolute;
		top: -3px;
		bottom: -3px;
		width: 2px;
		background: var(--warn);
	}
	.bar-legend {
		display: flex;
		flex-wrap: wrap;
		gap: 16px;
		margin-top: 10px;
		font-size: 13px;
		color: var(--text);
	}
	.sw {
		display: inline-block;
		width: 11px;
		height: 11px;
		border-radius: 2px;
		vertical-align: middle;
		margin-right: 3px;
	}
	.sw.fill {
		background: #1f6f68;
	}
	.sw.tick {
		background: var(--warn);
	}

	.cta {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		margin: 24px 0 8px;
	}
	.cta-btn {
		padding: 9px 14px;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--surface);
		color: var(--text);
		font-size: 14px;
	}
	.cta-btn:hover {
		border-color: var(--accent);
		text-decoration: none;
	}
	.cta-btn.primary {
		background: var(--accent);
		color: #fff;
		border-color: var(--accent);
	}
	code {
		background: var(--surface-2);
		padding: 1px 5px;
		border-radius: 5px;
		font-size: 13px;
	}
</style>
