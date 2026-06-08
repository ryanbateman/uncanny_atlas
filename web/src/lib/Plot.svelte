<script lang="ts">
	import type * as PlotNS from '@observablehq/plot';

	// Renders an Observable Plot chart (client-side only). The `render` prop
	// receives the Plot namespace plus the measured container width, so marks are
	// built from the dynamically-imported module and the chart fills its panel.
	let { render }: { render: (Plot: typeof PlotNS, opts: { width: number }) => HTMLElement | SVGElement } =
		$props();
	let el: HTMLDivElement;
	let mod = $state<typeof PlotNS | null>(null);
	let width = $state(0);

	// Load the plotting library once (client only; kept out of the SSR render).
	import('@observablehq/plot').then((m) => {
		mod = m;
	});

	// Track the container's available width so the chart can render full-bleed
	// (Plot defaults to 640px otherwise, leaving the panel ~40% empty).
	$effect(() => {
		if (!el) return;
		const ro = new ResizeObserver((entries) => {
			const w = entries[0]?.contentRect.width ?? 0;
			if (w) width = Math.round(w);
		});
		ro.observe(el);
		return () => ro.disconnect();
	});

	$effect(() => {
		const build = render;
		const Plot = mod;
		const w = width;
		if (!Plot || !el || !w) return;
		// Call build() synchronously here so any reactive state the render function
		// reads (e.g. `data.overTime`) is tracked as a dependency of this effect.
		// Building inside an async .then() would read that data outside the tracking
		// scope, so the chart would never update on client-side navigation.
		const node = build(Plot, { width: w }) as Element & { remove(): void };
		el.replaceChildren(node);
		return () => node.remove();
	});
</script>

<div class="chart" bind:this={el}></div>
