import type { Handle } from '@sveltejs/kit';
import { error } from '@sveltejs/kit';
import { dev } from '$app/environment';
import { isReadonly } from '$lib/server/cache';

/** Cookie that, in dev only, overrides the read-only view for layout debugging. */
export const RO_COOKIE = 'ua_ro';

/**
 * Effective read-only state for a request. In production it's purely the
 * ISTHISAI_READONLY env flag. In dev a `ua_ro` cookie (1/0) can override it, so
 * the in-app toggle can flip every page's read-only view without a restart.
 * Note: the DB handle's open mode (db.ts) and the cache memoization still follow
 * the env flag — the override only affects what the UI renders, which is all the
 * toggle is for.
 */
function effectiveReadonly(cookies: { get(name: string): string | undefined }): boolean {
	if (dev) {
		const override = cookies.get(RO_COOKIE);
		if (override === '1') return true;
		if (override === '0') return false;
	}
	return isReadonly;
}

export const handle: Handle = async ({ event, resolve }) => {
	event.locals.readonly = effectiveReadonly(event.cookies);

	// Read-only deployment guard. Curate writes all go through POST form actions
	// under /curate/**, so one chokepoint covers every mutation.
	if (
		event.locals.readonly &&
		event.request.method === 'POST' &&
		event.url.pathname.startsWith('/curate')
	) {
		throw error(403, 'Uncanny Atlas is running in read-only mode; curation is disabled.');
	}
	return resolve(event);
};
