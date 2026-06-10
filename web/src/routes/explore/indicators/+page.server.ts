import type { PageServerLoad } from './$types';
import { building } from '$app/environment';
import * as q from '$lib/server/queries';
import { cached, isReadonly, READONLY_CACHE_CONTROL } from '$lib/server/cache';

const GRANS = ['week', 'month'] as const;

export const load: PageServerLoad = ({ url, setHeaders, locals }) => {
	// setHeaders is invalid while prerendering; only the live SSR/node deploy uses it.
	if (isReadonly && !building) setHeaders({ 'cache-control': READONLY_CACHE_CONTROL });

	// The `category` query param only drives the example-comment table, which is
	// hidden in read-only mode. During prerender the query string is inaccessible,
	// so default it; live (SSR) reads it normally.
	const search = building ? '' : url.search;
	const categoryParam = building ? '' : url.searchParams.get('category') || '';

	return cached(`indicators:${search}`, () => {
		// De-dupe by post is always on: the over-time charts count each post once per
		// cue (not once per comment), so a single viral post can't dominate a trend.
		const dedupeByPost = true;
		// Category-decomposition charts ship WITH the Noise category so each can toggle
		// it client-side; rankings + the source breakdown exclude Noise.
		const withNoise = { excludeNoise: false };
		const clean = { excludeNoise: true };

		const categories = q.indicatorCategories();
		const category = categoryParam || categories[0] || '';

		// Pre-compute every granularity so each over-time chart can switch instantly
		// client-side. (De-dupe-by-post counts distinct posts per bucket, which can't be
		// re-aggregated from a finer bucket, so each granularity is computed in SQL.)
		const overTime = Object.fromEntries(
			GRANS.map((g) => [g, q.indicatorsOverTime({ ...withNoise, granularity: g, dedupeByPost })])
		);
		const topOverTime = Object.fromEntries(
			GRANS.map((g) => [
				g,
				q.topIndicatorsOverTime({ ...clean, granularity: g, topN: 10, dedupeByPost })
			])
		);
		const periods = Object.fromEntries(GRANS.map((g) => [g, q.contiguousBuckets(g)]));

		return {
			categories,
			category,
			categoryCounts: q.indicatorCategoryCounts(withNoise),
			domain: q.overTimeDomain(),
			periods,
			overTime,
			topOverTime,
			bySubreddit: q.indicatorsBySubreddit(withNoise),
			sources: q.indicatorSourceCounts(clean),
			// Media-dimensioned rows (union of per-facet top-40s); the client
			// re-ranks for the selected media filter and slices the top 40.
			top: q.topIndicatorsByMedia({ ...clean, limit: 40 }),
			// canonical -> member phrases, for the "N merged" badge on the top table + legend.
			mergeGroups: Object.fromEntries(
				q.mergeGroups().map((g) => [g.canonical, g.members] as [string, string[]])
			),
			// Read-only public edition serves aggregate-only data: no verbatim comment
			// examples (see Part J / the About page). Skip the query entirely.
			examples: !locals.readonly && category ? q.indicatorExampleComments(category, 12) : []
		};
	});
};
