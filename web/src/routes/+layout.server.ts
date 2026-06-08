import type { LayoutServerLoad } from './$types';
import { dev } from '$app/environment';

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
	return { readonly: locals.readonly, dev };
};
