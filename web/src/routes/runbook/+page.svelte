<script lang="ts">
	import { n } from '$lib/format';
	let { data } = $props();
	const s = $derived(data.status);

	// Each pipeline step: command(s), what it writes, a live count, and a link into
	// the conceptual explainer (How it works) for the matching idea.
	const steps = $derived([
		{
			title: '1 · Collect raw Reddit data',
			cmd: 'uv run isthisai-collect submissions\nuv run isthisai-collect comments\n# other subreddit:\nuv run isthisai-collect comments --subreddit RealOrAI',
			make: 'make collect',
			output:
				'Fetches every submission and comment from the subreddits via the PullPush API into the submissions and comments tables. No labels yet.',
			stat: { label: 'comments collected', value: data.counts.comments },
			explain: { href: '/how-it-works#problem', label: 'the problem' }
		},
		{
			title: '2 · Fill gaps from Arctic Shift (optional)',
			cmd: 'uv run isthisai-import api submissions\nuv run isthisai-import api comments\n# or from downloaded dumps:\nuv run isthisai-import file comments data/RC_*.zst',
			make: 'make import-arctic-api',
			output:
				'PullPush can miss windows of history. Arctic Shift backfills missing submissions/comments into the same tables (deduplicated on id).',
			stat: { label: 'submissions', value: data.counts.submissions }
		},
		{
			title: '3 · Extract indicators with the LLM (sample)',
			cmd: 'uv run isthisai-extract sample',
			output:
				'Filters to opinion comments (keyword + length, minus bots/deleted), randomly samples a few thousand (default 2,500), and asks gemma3:4b (Ollama) for the indicators cited in each comment - one comment per call, so every indicator is tied to the right comment. Each indicator becomes a row in comment_indicators with category = NULL.',
			stat: { label: 'LLM-extracted rows', value: s.llm },
			explain: { href: '/how-it-works#extraction', label: 'reading the comments' }
		},
		{
			title: '4 · Build the taxonomy (the seeds)',
			cmd: 'uv run isthisai-extract taxonomy',
			output:
				'Takes the ~200 most frequent indicator phrases and asks the LLM to sort each into one of the categories. These become the seeds that semantic expansion hunts from. Writes indicator_taxonomy, then backfills the category on every matching comment_indicators row.',
			stat: { label: 'taxonomy indicators (seeds)', value: s.taxonomy },
			explain: { href: '/how-it-works#seeds', label: 'seeds' }
		},
		{
			title: '5 · Embed taxonomy + comments',
			cmd: 'uv run isthisai-embed indicators\nuv run isthisai-embed comments --all',
			output:
				'Generates 768-dim nomic-embed-text vectors for taxonomy indicators (indicator_embeddings) and comment bodies (comment_embeddings). Add --all to embed the whole corpus, not just indicator-bearing comments - the single biggest lever on semantic coverage. Expensive but resumable.',
			stat: { label: 'embedded comments', value: s.embeddedComments },
			explain: { href: '/how-it-works#embeddings', label: 'the map of meaning' }
		},
		{
			title: '6 · Ground (drop hallucinated indicators)',
			cmd: 'uv run isthisai-embed ground',
			output:
				"The text-only model sometimes invents an indicator for a comment that just reacts (\"it's obviously AI\"). This compares each LLM indicator's embedding to its comment's embedding and deletes the ones below the grounding threshold (default 0.45). Semantic and keyword rows are left alone.",
			stat: { label: 'LLM-extracted rows', value: s.llm },
			explain: { href: '/how-it-works#extraction', label: 'why it hallucinates' }
		},
		{
			title: '7 · Semantic expansion',
			cmd: 'uv run isthisai-embed semantic',
			output:
				'Compares every comment embedding to every seed (taxonomy-indicator) embedding; above the similarity threshold (default 0.73) it inserts a new comment_indicators row (batch_id semantic_*). Only comments ≥20 chars (non-bot, non-[deleted]) are matched - the same length gate as the LLM sample, so one-word/emoji reactions are excluded. Seeds a curator marked Noise are skipped. This is how coverage grows beyond the LLM sample - re-run it after embedding more comments.',
			stat: { label: 'semantic matches', value: s.semantic },
			explain: { href: '/how-it-works#expansion', label: 'finding the neighbours' }
		},
		{
			title: '8 · Inspect anytime',
			cmd: 'uv run isthisai-stats',
			make: 'make stats',
			output:
				'Prints corpus counts and date ranges to the terminal. Or just use the Explore tabs in this app - they read the same database live.',
			stat: { label: 'indicator aliases (merges)', value: s.aliases }
		}
	]);
</script>

<h2>Run book</h2>
<p class="page-desc">
	The hands-on, terminal-facing companion to <a href="/">How it works</a> - the same pipeline, but as
	commands you can run and counts you can watch. Each step links back to the idea it implements.
</p>

<h3>Running the pipeline</h3>
<p class="page-desc">
	Steps run in order; each is resumable and safe to re-run. Steps 3–7 need a local
	<a href="https://ollama.com">Ollama</a> server with <code>gemma3:4b</code> and
	<code>nomic-embed-text</code> pulled. Commands assume <code>uv sync --all-extras</code> has been run.
</p>

{#each steps as step (step.title)}
	<div class="panel step">
		<div class="step-head">
			<h4>{step.title}</h4>
			<div class="step-stat">
				<span class="value">{n(step.stat.value)}</span>
				<span class="label">{step.stat.label}</span>
			</div>
		</div>
		<pre>{step.cmd}</pre>
		{#if step.make}<div class="shortcut">shortcut: <code>{step.make}</code></div>{/if}
		<p class="output">{step.output}</p>
		{#if step.explain}<a class="explain-link" href={step.explain.href}>→ How it works: {step.explain.label}</a>{/if}
	</div>
{/each}

<h3 id="filters">The two upstream filters</h3>
<p class="page-desc">
	Before the model reads anything, two hand-maintained lists in <code>extract.py</code> shape the
	input - and both materially affect the rankings, so they're worth understanding before trusting the
	numbers.
</p>
<div class="panel">
	<table>
		<thead><tr><th>Filter</th><th>What it does &amp; why</th><th>Current value</th></tr></thead>
		<tbody>
			<tr>
				<td><strong>Candidate keywords</strong><br /><code>OPINION_KEYWORDS</code></td>
				<td>
					Selects which comments are <em>eligible</em> for the LLM sample - a comment must contain at
					least one (and be ≥20 chars, non-bot). Deliberately <strong>topical, not visual-indicator</strong>
					words: filtering for “finger”/“shadow” would pre-decide the findings (you'd only “discover”
					the indicators you searched for). Broad on purpose - semantic expansion handles recall.
				</td>
				<td class="pill-list">
					<span class="pill">AI</span> <span class="pill">real</span> <span class="pill">fake</span>
					<span class="pill">generated</span> <span class="pill">obvious</span> <span class="pill">look</span>
				</td>
			</tr>
			<tr>
				<td><strong>Stop-list</strong><br /><code>STOP_INDICATORS</code></td>
				<td>
					Drops a returned “indicator” if it's never a property of the image. Exact, case-insensitive match.
					Two kinds get dropped: where an image was <em>posted</em>, and pure <strong>verdicts</strong> ("definitely AI", "not AI") that are judgements, not evidence, and otherwise swamp the rankings. Generation tools, bare subjects and watermarks are deliberately kept in: a <em>SynthID watermark</em> is strong evidence of AI, not noise. Exact, case-insensitive match; the full list lives in extract.py.
				</td>
				<td class="pill-list"><span class="pill">facebook</span> <span class="pill">tiktok</span> <span class="pill">reddit</span> <span class="pill">definitely ai</span> <span class="pill">not ai</span> <span class="pill">obviously ai</span> <span class="pill">100% ai</span> <span class="pill">ai generated</span> <span class="pill">ai slop</span></td>
			</tr>
		</tbody>
	</table>
</div>

<h3 id="levers">Improving accuracy</h3>
<p class="page-desc">
	Automated extraction is imperfect - the LLM mislabels, the keyword filter lets noise through, and
	semantic expansion has no notion of “correct”. These are the levers, cheapest first (the ideas
	behind them are in <a href="/how-it-works#cleanup">How it works → cleaning up</a>).
</p>

<div class="panel">
	<table>
		<thead><tr><th>Lever</th><th>What it does</th><th>Where</th></tr></thead>
		<tbody>
			<tr>
				<td><strong>Mark Noise</strong></td>
				<td>Tag phrases that aren't real indicators (vague judgments, meta-commentary). Cascades to every comment using the phrase <em>and</em> writes through to the taxonomy, so it's durable - a later semantic re-expansion won't reintroduce it (Noise phrases stop being expanded).</td>
				<td><a href="/curate/indicators">Curate → Indicators</a></td>
			</tr>
			<tr>
				<td><strong>Re-categorise phrases</strong></td>
				<td>Move an indicator to the right category. One change backfills all rows sharing that phrase - highest leverage per click.</td>
				<td><a href="/curate/indicators">Curate → Indicators</a></td>
			</tr>
			<tr>
				<td><strong>Fix the taxonomy</strong></td>
				<td>Edit the source-of-truth indicator/category. Backfills existing rows <em>and</em> steers all future semantic expansion - fixes the root cause, not just symptoms.</td>
				<td><a href="/curate/indicators">Curate → Indicators</a></td>
			</tr>
			<tr>
				<td><strong>Merge near-duplicates</strong></td>
				<td>Consolidate scattered phrasings (“wrong hands”, “funny hands”, “hands look messed up”) into one <a href="/how-it-works#merging">canonical indicator (a merged group)</a>, so frequency counts reflect the real concept rather than splitting across synonyms.</td>
				<td><a href="/curate/merge">Curate → Merge</a></td>
			</tr>
			<tr>
				<td><strong>Tune the similarity threshold</strong></td>
				<td>Lower the 0.73 default for more coverage (more false positives); raise it for higher precision (fewer matches). Re-run <code>isthisai-embed semantic</code> after changing <code>ISTHISAI_EMBED_THRESHOLD</code>.</td>
				<td>pipeline, step 7</td>
			</tr>
			<tr>
				<td><strong>Extract a larger sample</strong></td>
				<td>Run LLM extraction over more comments for broader, higher-confidence coverage before relying on semantic expansion to fill the rest.</td>
				<td>pipeline, step 3</td>
			</tr>
			<tr>
				<td><strong>Widen embedding coverage</strong></td>
				<td>By default only indicator-bearing comments are embedded, so semantic expansion searches a tiny pool. Embed the whole corpus, then re-expand, to surface indicator mentions in comments the sample never touched - the biggest lever on how representative the counts are.</td>
				<td><code>isthisai-embed comments --all</code></td>
			</tr>
			<tr>
				<td><strong>Rename an indicator / drop a bad comment</strong></td>
				<td>Pick any indicator, see every comment that cites it, then rename the canonical or remove an obviously mis-attributed comment from it.</td>
				<td><a href="/explore/lookup">Explore: Inspect indicator</a></td>
			</tr>
			<tr>
				<td><strong>Remove bad indicators</strong></td>
				<td>Deleting a taxonomy indicator stops it being re-created on the next semantic run - the only way to permanently suppress a bad expansion source.</td>
				<td><a href="/curate/indicators">Curate → Indicators</a></td>
			</tr>
		</tbody>
	</table>
</div>

<h3>Beyond the pipeline</h3>
<div class="panel">
	<p class="output" style="margin: 0">
		The refined <code>comment_indicators</code> data (verified indicators + categories) can be
		exported as JSONL to fine-tune a replacement for <code>gemma3:4b</code>. Point the pipeline at
		the new model via <code>ISTHISAI_OLLAMA_MODEL</code>; see the project README for the export and
		training steps.
	</p>
</div>

<style>
	.step-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 16px;
	}
	.step-head h4 {
		margin: 0 0 8px;
		font-size: 15px;
	}
	.step-stat {
		text-align: right;
		white-space: nowrap;
	}
	.step-stat .value {
		font-weight: 700;
		font-size: 16px;
	}
	.step-stat .label {
		color: var(--muted);
		font-size: 11px;
		margin-left: 6px;
	}
	pre {
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 10px 12px;
		overflow-x: auto;
		font-size: 12.5px;
		margin: 0 0 8px;
	}
	.shortcut {
		color: var(--muted);
		font-size: 12px;
		margin-bottom: 8px;
	}
	.output {
		margin: 0 0 8px;
		color: var(--text);
	}
	.explain-link {
		font-size: 12px;
		color: var(--accent);
	}
	code {
		background: var(--surface-2);
		padding: 1px 5px;
		border-radius: 5px;
		font-size: 12px;
	}
</style>
