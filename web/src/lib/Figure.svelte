<script lang="ts">
	import type { Snippet } from 'svelte';
	import Hint from '$lib/Hint.svelte';

	// Standard wrapper for a chart-as-content: title (+ optional hint) and optional
	// controls in the header, the chart as children, and an optional caption. Keeps
	// every chart in the app consistent with the /styleguide reference.
	let {
		title,
		hint = undefined,
		caption = undefined,
		controls = undefined,
		children
	}: {
		title: string;
		hint?: string;
		caption?: string;
		controls?: Snippet;
		children: Snippet;
	} = $props();
</script>

<figure class="figure">
	<div class="figure-head">
		<h3 class="figure-title">{title}{#if hint}<Hint text={hint} />{/if}</h3>
		{#if controls}<div class="figure-controls">{@render controls()}</div>{/if}
	</div>
	{@render children()}
	{#if caption}<figcaption>{caption}</figcaption>{/if}
</figure>
