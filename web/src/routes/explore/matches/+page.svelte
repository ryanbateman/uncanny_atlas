<script lang="ts">
	import Hint from '$lib/Hint.svelte';
	import SelfHostNotice from '$lib/SelfHostNotice.svelte';
	import { n } from '$lib/format';
	let { data } = $props();

	const pageUrl = (offset: number) => {
		const p = new URLSearchParams();
		if (data.category) p.set('category', data.category);
		if (data.search) p.set('search', data.search);
		p.set('limit', String(data.limit));
		if (offset > 0) p.set('offset', String(offset));
		return `?${p}`;
	};
</script>

<h2>Semantic matches</h2>
<p class="page-desc">
	Read-only audit of indicators added by embedding-based semantic expansion (rows whose batch is
	<code>semantic_*</code>). Use this to judge expansion quality.
</p>

{#if data.readonly}
	<SelfHostNotice what="Semantic-match comments" />
{:else}
<div class="table-card">
<form class="filter-bar table-controls" method="get">
	<label>
		Category
		<select name="category" onchange={(e) => e.currentTarget.form?.requestSubmit()}>
			<option value="">All</option>
			{#each data.categories as c (c)}
				<option value={c} selected={c === data.category}>{c}</option>
			{/each}
		</select>
	</label>
	<label>
		Search
		<input type="search" name="search" value={data.search} placeholder="indicator or comment…" />
	</label>
	<button type="submit">Filter</button>
</form>

{#if data.rows.length}
<div class="table-scroll">
	<table>
		<thead>
			<tr>
				<th>Comment <Hint text="The comment a semantic match was attached to — it may not contain the exact words; the match is by meaning." /></th>
				<th>Matched indicators <Hint text="All taxonomy indicators this comment was matched to by semantic expansion (alias-resolved, de-duplicated). Comments matching the most indicators are listed first." /></th>
				<th>Sub</th>
			</tr>
		</thead>
		<tbody>
			{#each data.rows as row (row.id)}
				<tr>
					<td class="truncate" title={row.body}>{row.body}</td>
					<td>
						<div class="pill-list">
							{#each row.indicators.split(',') as ind (ind)}<span class="pill">{ind.trim()}</span>{/each}
						</div>
					</td>
					<td>{row.subreddit}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{:else}
<div class="table-empty">No semantic matches for these filters.</div>
{/if}
{#if data.total > data.limit}
<div class="table-foot">
	<span>{data.offset + 1}–{Math.min(data.offset + data.limit, data.total)} of {n(data.total)}</span>
	<span class="pager">
		{#if data.offset > 0}<a href={pageUrl(Math.max(data.offset - data.limit, 0))}>← Prev</a>{/if}
		{#if data.offset + data.limit < data.total}<a href={pageUrl(data.offset + data.limit)}>Next →</a>{/if}
	</span>
</div>
{/if}
</div>
{/if}
