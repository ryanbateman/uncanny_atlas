import type { PageServerLoad } from './$types';
import * as q from '$lib/server/queries';

export const load: PageServerLoad = () => {
	// Same shared source as the About page (q.headlineStats()) so the two never diverge.
	return q.headlineStats();
};
