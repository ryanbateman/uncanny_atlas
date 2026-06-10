<script lang="ts">
	import { n } from '$lib/format';
	let { data } = $props();

	// Single edit points for publication details. Fill these in before going public.
	const REPO_URL = 'https://github.com/ryanbateman/uncanny_atlas';
	const CONTACT = 'mailto:ryan.bateman@gmail.com';
</script>

<div class="reader">
	<h1>Uncanny Atlas</h1>
	<p class="lede">
		This project is a personal study. I wanted to explore when people started worrying about photos and video content being AI-generated, as well as <em>what signs people were using to try spot AI-generated images</em>.<br/><br/> 

		This website is an overview of my results so far. It is also the dashboard for the tool I built to conduct this exploration. You can run this tool locally yourself.<br/> 
		<br/>When run, the tool downloads the comments from
		<a href="https://reddit.com/r/isthisAI">r/isthisAI</a> and
		<a href="https://reddit.com/r/RealOrAI">r/RealOrAI</a>, pulls out the “indicators” people cite - wrong hands, impossible shadows, garbled text - and maps them with language-model embeddings into a tally of the indicators people <em>actually</em> rely on. I then curate these to group them and turn them into an understandable dataset. <br/><br/>
		It is currently based on
		<strong>{n(data.totalComments)}</strong> comments. {#if data.eligible && data.analysed != null && data.analysedReal != null}Of the <strong>{n(data.eligible)}</strong>
substantive comments, the pipeline has flagged <strong>{n(data.analysed)}</strong> ({(100 * data.analysed / data.eligible).toFixed(1)}%) as citing a possible indicator; after curation, <strong>{n(data.analysedReal)}</strong> ({(100 * data.analysedReal / data.eligible).toFixed(1)}%) cite a genuine visual tell.{/if}{#if data.top}<br/><br/>In the current dataset the most-cited indicator is <span class="chip">{data.top.indicator}</span> with <strong>{n(data.top.count)}</strong> comments.
		{/if}
	</p>

	<div class="cta">
		<a class="cta-btn primary" href="/explore/indicators">Explore the results →</a>
		<a class="cta-btn" href="/how-it-works">How it works →</a>
		<a class="cta-btn" href="/runbook">Run book →</a>
	</div>

	<h2 id="what">What you can do here</h2>
	<p>
		<a href="/how-it-works">How it works</a> is a from-first-principles, interactive explainer of the
		whole method — keyword matching's failure, the language-model reader, the “map of meaning”, and
		semantic expansion.<br/><br/>The <a href="/explore/indicators">Explore</a> views show the live results from my run and curation of the data:
		the most-cited indicators, how they trend over time, and generally how the subreddits have grown.<br/><br/> The
		<a href="/runbook">Run book</a> documents the pipeline end to end so you can rebuild it yourself.<br/><br/>
		
	</p>

	<h2 id="editions">This site vs. running it yourself</h2>
	{#if data.readonly}
		<p>
			You're viewing the <strong>public, read-only edition</strong> of my run at exploring this data. To keep within Reddit's content
			terms and data-protection law, it serves only <em>aggregate</em> results — counts, trends and
			breakdowns — and deliberately leaves a few things out:
		</p>
	{:else}
		<p>
			You're running Uncanny Atlas <strong>locally</strong>, so you have the full experience. For
			reference, the <strong>public, read-only edition</strong> deliberately leaves a few things out,
			to stay within Reddit's content terms and data-protection law (it serves only aggregate results):
		</p>
	{/if}
	<div class="cmp">
		<table>
			<thead>
				<tr><th>Capability</th><th>This site</th><th>Self-hosted</th></tr>
			</thead>
			<tbody>
				<tr>
					<td>Example comments (Indicators, Inspect, Semantic matches)</td>
					<td class="off">Hidden</td>
					<td class="on">Full comment text</td>
				</tr>
				<tr>
					<td>Curate workflow (categorise indicators, merge)</td>
					<td class="off">Off</td>
					<td class="on">Available</td>
				</tr>
				<tr>
					<td>Underlying data</td>
					<td class="off">Frozen aggregate snapshot</td>
					<td class="on">Live database + pipeline</td>
				</tr>
				<tr>
					<td>Pipeline (collect → extract → embed)</td>
					<td class="off">Not runnable</td>
					<td class="on">Runnable (needs Ollama)</td>
				</tr>
			</tbody>
		</table>
	</div>
	<p class="why">
		Why: the verbatim comments belong to their Reddit authors, not to this project, and a frozen
		public copy couldn't honour later deletions — so this public, personal data exploration can only contain only the derived
		statistics, never the raw text or usernames. Running it yourself, against the comments and data you have collected using the tool, removes that constraint. See the <a href="/runbook">Run book</a> to get started.
	</p>

	<h2 id="credits">Credits &amp; attribution</h2>
	<ul class="credits">
		<li>
			<strong>Data.</strong> Public comments from Reddit (<a href="https://reddit.com/r/isthisAI"
				>r/isthisAI</a
			>, <a href="https://reddit.com/r/RealOrAI">r/RealOrAI</a>), retrieved via the
			<a href="https://pullpush.io">PullPush</a> and
			<a href="https://arctic-shift.photon-reddit.com">Arctic Shift</a> public archives. Reddit and
			the comment authors retain all rights to the original content.
		</li>
		<li>
			<strong>Models.</strong> For this run, I used with <code>gemma3:4b</code> and embeddings with
			<code>nomic-embed-text</code>, both run locally via <a href="https://ollama.com">Ollama</a>. If running locally, these can be configured.
		</li>
		<li>
			<strong>Built with.</strong> <a href="https://kit.svelte.dev">SvelteKit</a>,
			<a href="https://observablehq.com/plot/">Observable Plot</a>, and
			<a href="https://github.com/WiseLibs/better-sqlite3">better-sqlite3</a>.
		</li>
		<li>
			<strong>Type.</strong> Display face <em>Captain Edward</em> by
			<a href="https://simplebits.shop">SimpleBits</a> (live site only); body text in
			<a href="https://rsms.me/inter/">Inter</a>.
		</li>
		<li>
			<strong>Code.</strong> Open source under the MIT license —
			<a href={REPO_URL}>{REPO_URL.replace('https://', '')}</a>.
		</li>
	</ul>
	<p class="noncommercial">
		Uncanny Atlas is a non-commercial research showcase and intentionally does not include any particular user data. If you are a Reddit user and somehow find a
		contribution of yours included, <a href={CONTACT}>contact us</a> and it will be removed from the
		next rebuild. The public snapshot is periodically rebuilt from the upstream archives, which
		propagate deletions.
	</p>

	<h2 id="limits">Methodology &amp; limitations</h2>
	<p>
		The headline method is on the <a href="/how-it-works">How it works</a> page. Read the numbers
		with these caveats in mind:
	</p>
	<ul class="limits">
		<li>
			<strong>Individual perspective.</strong> Creating this dataset involves curating data into categories, picking similarity values, and making personal choices about what constituted a datapoint. Other people will pick other categories, make other choices. This data is not intended to be regarded as objectively correct, and the project is intentionally open-source so that others can run it themselves with their own approach/choices.
		</li>
		<li>
			<strong>Recency.</strong> The corpus skews to recent activity (~2025 onward), so trends say
			more about the present than the early history of AI imagery.
		</li>
		<li>
			<strong>Selection.</strong> Only two subreddits feed it (r/isthisAI, r/RealOrAI); their
			audiences and norms shape which indicators surface.
		</li>
		<li>
			<strong>Pre-and-post filters.</strong> I made personal judgements regarding which comments were worth sampling. There is a keyword filter and a
			~20-character length floor, which drops very short or off-topic reactions.
		</li>
		<li>
			<strong>Sample + expansion.</strong> Only a few thousand comments are read by the language
			model; the rest are reached by embedding similarity. The expansion threshold (0.73) and the
			grounding threshold (0.45) trade coverage against precision.
		</li>
		<li>
			<strong>Model bias.</strong> Both the extractor and the embedder carry their own biases. Different models will draw the map differently.
		</li>
		<li>
			<strong>Human-in-the-loop.</strong> Indicator merging and noise removal are curated by (my) hand, which
			adds judgement (and the possibility of error) to the canonical labels.
		</li>
	</ul>
</div>

<style>
	.reader {
		max-width: var(--reader-width);
		margin: 0 auto;
		font-size: var(--text-md);
		line-height: 1.7;
	}
	.reader h1 {
		font-size: var(--text-3xl);
		line-height: 1.1;
		margin: 4px 0 16px;
	}
	.reader h2 {
		font-size: var(--text-xl);
		margin: 44px 0 6px;
		scroll-margin-top: 16px;
	}
	.reader p {
		margin: 12px 0;
		color: var(--text);
	}
	.lede {
		font-size: var(--text-lg);
	}
	.chip {
		display: inline-block;
		padding: 1px 8px;
		margin: 0 1px;
		border: 1px solid var(--border);
		border-left: 3px solid var(--accent);
		border-radius: 6px;
		font-size: var(--text-sm);
		background: var(--surface);
		white-space: nowrap;
	}

	.cta {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		margin: 20px 0 8px;
	}
	.cta-btn {
		padding: 9px 14px;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		background: var(--surface);
		color: var(--text);
		font-size: var(--text-base);
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

	.cmp {
		margin: 16px 0;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		overflow: hidden;
	}
	.cmp table {
		width: 100%;
		border-collapse: collapse;
		font-size: var(--text-sm);
	}
	.cmp th,
	.cmp td {
		text-align: left;
		padding: 9px 12px;
		border-bottom: 1px solid var(--border);
		vertical-align: top;
	}
	.cmp thead th {
		background: var(--surface-2);
		color: var(--muted);
		font-weight: 600;
	}
	.cmp tbody tr:last-child td {
		border-bottom: none;
	}
	.cmp td.on {
		color: var(--good-text);
		white-space: nowrap;
	}
	.cmp td.off {
		color: var(--muted);
		white-space: nowrap;
	}
	.why {
		font-size: var(--text-sm);
		color: var(--muted);
	}

	.credits,
	.limits {
		padding-left: 20px;
		margin: 12px 0;
	}
	.credits li,
	.limits li {
		margin: 8px 0;
		color: var(--text);
	}
	.noncommercial {
		font-size: var(--text-sm);
		color: var(--muted);
		border-left: 3px solid var(--border);
		padding-left: 12px;
	}
	code {
		background: var(--surface-2);
		padding: 1px 5px;
		border-radius: 5px;
		font-size: var(--text-sm);
	}
</style>
