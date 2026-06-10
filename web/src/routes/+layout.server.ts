import type { LayoutServerLoad } from './$types';
import { dev } from '$app/environment';
import { dataAsOf } from '$lib/server/queries';

/**
 * Prerender the whole site only for the static public target (BUILD_TARGET=static).
 * The adapter-node build leaves this false, so it stays SSR (no DB at build, data
 * fetched per request). Routes that can't be static — /curate (form actions) and
 * the comment-only /explore/lookup + /explore/matches — override this to false.
 */
export const prerender = process.env.BUILD_TARGET === 'static';

/**
 * Expose the effective read-only flag (computed per request in hooks.server.ts)
 * so the layout can hide the Curate / comment-only nav, and `dev` so the dev-only
 * read-only toggle is rendered only in development.
 */
export const load: LayoutServerLoad = ({ locals }) => {
	// snapshot: stamped into the footer so every page (and anyone quoting a
	// number) can anchor it to a data date. Cheap (two indexed lookups + COUNT).
	return { readonly: locals.readonly, dev, snapshot: dataAsOf() };
};
