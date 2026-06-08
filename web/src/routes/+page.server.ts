import type { PageServerLoad } from './$types';
import * as q from '$lib/server/queries';
import { isReadonly } from '$lib/server/cache';

export const load: PageServerLoad = () => {
	// Headline figures (top indicator, coverage, totals) come from the one shared source so
	// this page and How-it-works can never show different numbers — see q.headlineStats().
	return { readonly: isReadonly, ...q.headlineStats() };
};
