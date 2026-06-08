import { building } from '$app/environment';
import type { PageServerLoad } from './$types';
import * as q from '$lib/server/queries';

// Inherits the root layout's `prerender = (BUILD_TARGET === 'static')`:
//  - static build -> prerendered as the read-only self-host notice (so nav/links resolve
//    instead of 404ing).
//  - node build   -> the live semantic-matches table at runtime.
export const load: PageServerLoad = ({ url, locals }) => {
	// No request URL / searchParams during the static prerender; the page renders the
	// read-only notice anyway, so return a minimal payload.
	if (building) {
		return { rows: [], total: 0, limit: 50, offset: 0, category: '', search: '', categories: [] };
	}
	const category = url.searchParams.get('category') || undefined;
	const search = url.searchParams.get('search') || undefined;
	const limit = Number(url.searchParams.get('limit')) || 50;
	const offset = Number(url.searchParams.get('offset')) || 0;
	// Read-only public edition is aggregate-only: never serve verbatim comments
	// (see Part J / the About page).
	const { rows, total } = locals.readonly
		? { rows: [], total: 0 }
		: q.semanticMatches({ category, search, limit, offset });
	return {
		rows,
		total,
		limit,
		offset,
		category: category ?? '',
		search: search ?? '',
		categories: q.indicatorCategories()
	};
};
