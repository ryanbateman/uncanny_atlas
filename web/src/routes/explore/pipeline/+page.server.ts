import type { PageServerLoad } from './$types';
import * as q from '$lib/server/queries';
import * as curate from '$lib/server/curate';

export const load: PageServerLoad = () => {
	return { status: q.pipelineStatus(), pending: curate.pendingExpansion() };
};
