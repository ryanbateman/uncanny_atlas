import type { PageServerLoad } from './$types';
import * as q from '$lib/server/queries';

export const load: PageServerLoad = () => {
	const counts = q.totalCounts();
	const status = q.pipelineStatus();
	return {
		counts,
		status,
		indicatorsTotal: status.llm + status.semantic + status.keyword
	};
};
