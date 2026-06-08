/**
 * Read-only load() memoization.
 *
 * When the deployment is read-only (`ISTHISAI_READONLY` set), the database is
 * static, so caching a page's load() result by URL is always safe: the first hit
 * computes the (heavy) aggregates, every repeat is O(1). In a writable / local /
 * dev deployment this is a no-op, so curate edits are reflected immediately.
 *
 * Pairs with the read-only mode (db opened readonly + the /curate write guard).
 */
const flag = (process.env.ISTHISAI_READONLY ?? '').toLowerCase();
export const isReadonly = flag === '1' || flag === 'true' || flag === 'yes' || flag === 'on';

const store = new Map<string, unknown>();

/** Memoize `compute()` under `key` when read-only; otherwise just run it. */
export function cached<T>(key: string, compute: () => T): T {
	if (!isReadonly) return compute();
	if (store.has(key)) return store.get(key) as T;
	const value = compute();
	store.set(key, value);
	return value;
}

/** Cache-control for read-only responses, so a CDN/browser serves repeats. */
export const READONLY_CACHE_CONTROL = 'public, max-age=300';
