<script lang="ts">
	import { enhance } from '$app/forms';
	import Hint from '$lib/Hint.svelte';
	import SelfHostNotice from '$lib/SelfHostNotice.svelte';
	import { n } from '$lib/format';
	let { data, form } = $props();

	// Ensure the selected indicator is always an option (e.g. when arrived at via a
	// link from Top Indicators, the indicator may sit outside the capped suggestion list).
	const options = $derived.by(() => {
		const list = data.choices;
		if (data.indicator && !list.some((c) => c.indicator === data.indicator)) {
			return [{ indicator: data.indicator, comments: data.total }, ...list];
		}
		return list;
	});
</script>

<h2>Inspect indicator</h2>
<p class="page-desc">
	Pick a single indicator and see <strong>every comment</strong> that cites it — alias-resolved, so
	merged variants are included. Use this to sanity-check whether an indicator (e.g. "unnatural blinking")
	is being flagged correctly. The <code>Matched</code> column shows the raw phrase(s) the comment
	actually used, and <code>Found</code> shows whether each came from the LLM, semantic expansion, or
	keyword matching. You can <strong>rename</strong> the indicator or <strong>remove</strong> a comment that's
	obviously mis-attributed.
</p>

{#if data.readonly}
	<SelfHostNotice what="Per-comment inspection" />
{:else}
{#if form?.message}<div class="flash success">{form.message}</div>{/if}

<form class="filter-bar" method="get">
	<label>
		<span>Indicator <Hint text="Pick an indicator (canonical name, post-merge). The number is how many distinct comments cite it. Ordered by frequency." /></span>
		<select
			name="indicator"
			style="min-width:340px"
			onchange={(e) => e.currentTarget.form?.requestSubmit()}
		>
			<option value="" disabled selected={!data.indicator}>Pick an indicator…</option>
			{#each options as ch (ch.indicator)}
				<option value={ch.indicator} selected={ch.indicator === data.indicator}>
					{ch.indicator} ({n(ch.comments)})
				</option>
			{/each}
		</select>
	</label>
	<label style="flex-direction:row;align-items:center;gap:6px;color:var(--text)">
		<input
			type="checkbox"
			name="noise"
			value="show"
			checked={data.showNoise}
			onchange={(e) => e.currentTarget.form?.requestSubmit()}
		/>
		Show Noise <Hint text="Indicators tagged Noise are hidden from this list by default (they're excluded from charts and rankings anyway). Tick to include them." />
	</label>
	<noscript><button type="submit">Show comments</button></noscript>
</form>

{#if data.indicator}
	<form method="post" action="?/rename" use:enhance class="filter-bar rename-row">
		<label>
			<span>Rename indicator <Hint text="Renames this indicator everywhere it resolves — the old name and all its aliases become aliases of the new name, so every comment follows. Renaming to a name that already exists merges into it." /></span>
			<input type="text" name="newName" value={data.indicator} style="min-width:300px" />
		</label>
		<input type="hidden" name="indicator" value={data.indicator} />
		<button type="submit">Rename</button>
	</form>

	<p class="page-desc" style="margin-top:0">
		<strong>{n(data.total)}</strong> comment{data.total === 1 ? '' : 's'} cite
		<span class="pill">{data.indicator}</span>
		{#if data.members.length}<span class="merge-badge canon" title="Includes {data.members.length} merged variant(s): {data.members.join(', ')}">incl. {data.members.length} merged</span>{/if}
		{#if data.total > data.rows.length}<span class="hint-text">— showing the top {data.rows.length} by score</span>{/if}
	</p>
	<div class="table-card">
	{#if data.rows.length}
	<div class="table-scroll">
		<table>
			<thead>
				<tr>
					<th class="num">Score</th>
					<th>Sub</th>
					<th>Found <Hint text="How the indicator was attached to this comment: LLM extraction, semantic expansion, or keyword match." /></th>
					<th>Matched phrase(s) <Hint text="The raw indicator text in the comment that resolves to this canonical indicator." /></th>
					<th>Comment</th>
					<th><Hint text="Remove this comment's association with the indicator (deletes the link, not the comment). Use for obviously-wrong attributions." /></th>
				</tr>
			</thead>
			<tbody>
				{#each data.rows as r (r.id)}
					<tr>
						<td class="num">{n(r.score ?? 0)}</td>
						<td>{r.subreddit}</td>
						<td>{#each r.sources.split(',') as s (s)}<span class="pill">{s}</span> {/each}</td>
						<td>{#each r.matched.split(',') as m (m)}<span class="pill">{m}</span> {/each}</td>
						<td class="wrap" title={r.body}>{r.body}</td>
						<td>
							<form method="post" action="?/remove" use:enhance>
								<input type="hidden" name="indicator" value={data.indicator} />
								<input type="hidden" name="commentId" value={r.id} />
								<button class="remove" title="Remove this comment from the indicator">✕</button>
							</form>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{:else}
	<div class="table-empty">No comments cite this indicator.</div>
	{/if}
	</div>
{:else}
	<div class="panel">Pick an indicator above to see the comments that cite it.</div>
{/if}
{/if}

<style>
	.rename-row {
		margin-bottom: 14px;
	}
	.wrap {
		max-width: 600px;
		white-space: normal;
		word-break: break-word;
	}
	.hint-text {
		color: var(--muted);
	}
	.remove {
		background: transparent;
		border: none;
		color: var(--muted);
		font-size: var(--text-base);
		line-height: 1;
		padding: 2px 6px;
		cursor: pointer;
	}
	.remove:hover {
		color: var(--danger);
	}
</style>
