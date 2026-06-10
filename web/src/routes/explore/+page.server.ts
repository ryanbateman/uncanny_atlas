import type { PageServerLoad } from './$types';
import { building } from '$app/environment';
import * as q from '$lib/server/queries';
import { cached, isReadonly, READONLY_CACHE_CONTROL } from '$lib/server/cache';

export const load: PageServerLoad = ({ setHeaders }) => {
	// setHeaders is invalid while prerendering (the static target sets cache-control
	// at the web server instead); only set it for the live SSR/node deploy.
	if (isReadonly && !building) setHeaders({ 'cache-control': READONLY_CACHE_CONTROL });

	// Param-free: the over-time series ship at DAY granularity and each chart
	// re-buckets to its own granularity client-side. Counts/types cover all subreddits.
	return cached('overview', () => ({
		subreddits: q.distinctSubreddits(),
		counts: q.totalCounts(),
		range: q.dateRange(),
		submissionsOverTime: q.submissionsOverTimeBySubreddit({ granularity: 'day' }),
		commentsOverTime: q.commentsOverTimeBySubreddit({ granularity: 'day' }),
		types: q.mediaTypeBreakdown({}),
		typesOverTime: q.mediaTypeOverTime({ granularity: 'day' }),
		markers: q.timelineMarkers(),
		firstComment: q.firstCommentDate(),
		firstSubmission: q.firstSubmissionDate(),
		domain: q.overTimeDomain()
	}));
};
