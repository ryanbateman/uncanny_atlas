import { building } from '$app/environment';
import type { Actions, PageServerLoad } from './$types';
import { fail, redirect } from '@sveltejs/kit';
import * as q from '$lib/server/queries';
import * as curate from '$lib/server/curate';

// Inherits the root layout's `prerender = (BUILD_TARGET === 'static')`:
//  - static build -> prerendered as a single read-only page that shows the "self-host to
//    view comments" notice, so links to it (Top Indicators, About, How it works) resolve
//    instead of 404ing.
//  - node build   -> the live per-comment inspector at runtime, with the form actions below.
const isStatic = process.env.BUILD_TARGET === 'static';

export const load: PageServerLoad = ({ url, locals }) => {
	// No request URL / searchParams during the static prerender, and the page renders the
	// read-only notice anyway (data.readonly comes from the root layout), so return a
	// minimal payload and read nothing query-dependent.
	if (building) {
		return { indicator: '', choices: [], rows: [], total: 0, members: [], showNoise: false };
	}
	const indicator = (url.searchParams.get('indicator') ?? '').trim();
	// Noise-tagged indicators are hidden from the picker by default; the toggle shows them.
	const showNoise = url.searchParams.get('noise') === 'show';
	const choices = q.indicatorChoices(1000, showNoise);
	// Read-only public edition is aggregate-only: never serve verbatim comments
	// (see Part J / the About page).
	const result =
		!locals.readonly && indicator
			? q.commentsForIndicator(indicator, { limit: 300 })
			: { rows: [], total: 0 };
	// Member phrases folded into this canonical (for the "incl. N merged" header note).
	const members = indicator
		? (q.mergeGroups().find((g) => g.canonical === indicator)?.members ?? [])
		: [];
	return { indicator, choices, rows: result.rows, total: result.total, members, showNoise };
};

const liveActions = {
	rename: async ({ request }) => {
		const form = await request.formData();
		const oldName = String(form.get('indicator') ?? '').trim();
		const newName = String(form.get('newName') ?? '').trim();
		if (!oldName || !newName) return fail(400, { message: 'Provide a new name.' });
		if (oldName === newName) return fail(400, { message: 'New name is unchanged.' });
		curate.renameCanonical(oldName, newName);
		// The old name no longer exists — land on the renamed indicator.
		redirect(303, `/explore/lookup?indicator=${encodeURIComponent(newName)}`);
	},
	remove: async ({ request }) => {
		const form = await request.formData();
		const indicator = String(form.get('indicator') ?? '').trim();
		const commentId = String(form.get('commentId') ?? '').trim();
		if (!indicator || !commentId) return fail(400, { message: 'Missing comment or indicator.' });
		const removed = curate.removeAssociation(commentId, indicator);
		return { message: `Removed ${removed} association${removed === 1 ? '' : 's'} for that comment.` };
	}
} satisfies Actions;

// Form actions can't coexist with prerendering, and aren't needed in the read-only static
// build. Ship `undefined` there so the page prerenders, but keep the full type via the cast
// so the page's `form` prop stays correctly typed in the node build (SvelteKit's prerender
// check reads the runtime value, not the type).
export const actions = (isStatic ? undefined : liveActions) as typeof liveActions;
