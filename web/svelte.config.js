import { execSync } from 'node:child_process';
import adapterNode from '@sveltejs/adapter-node';
import adapterStatic from '@sveltejs/adapter-static';

// Version-skew protection: a deploy changes the data shapes the route code
// expects, so a tab loaded BEFORE the deploy that client-side-navigates AFTER
// it runs old code against new __data.json and dies mid-render ("page fails to
// load unless I hard reload"). Naming the version and polling lets SvelteKit
// detect the new deploy and turn the next navigation into a full-page load.
function buildVersion() {
	try {
		return execSync('git rev-parse --short HEAD').toString().trim();
	} catch {
		return String(Date.now()); // not a git checkout — any unique-ish value works
	}
}

// Two build targets from one source:
//   default            -> adapter-node  (local dev/curation + the Docker deploy)
//   BUILD_TARGET=static -> adapter-static (the frozen, prerendered public site)
// The static target is built with ISTHISAI_READONLY=1 so the read-only view is
// what gets baked in. See web/src/routes/+layout.server.ts (the `prerender` flag)
// and `npm run build:static`.
const isStatic = process.env.BUILD_TARGET === 'static';

// SAFETY: the static target prerenders against the FULL local DB, and verbatim
// comment text stays out of the output only because the read-only loads redact
// it. A static build without ISTHISAI_READONLY would bake Reddit comment bodies
// + usernames into public __data.json files. Refuse the combination outright —
// `npm run build:static` sets both, so only a hand-rolled build can get here.
// KEEP IN SYNC with the truthy-value list in src/lib/server/cache.ts (isReadonly).
const isReadonlyEnv = ['1', 'true', 'yes', 'on'].includes(
	(process.env.ISTHISAI_READONLY ?? '').toLowerCase()
);
if (isStatic && !isReadonlyEnv) {
	throw new Error(
		'BUILD_TARGET=static requires ISTHISAI_READONLY=1 — the public static build must ' +
			'be read-only or it bakes verbatim comment text into the prerendered output. ' +
			'Use `npm run build:static`, which sets both.'
	);
}

// Sub-path hosting (e.g. the static site served under boat.horse/atlas). Set via
// BASE_PATH; empty for root (local dev + the adapter-node deploy). The static build
// script sets BASE_PATH=/atlas. Must start with, and not end with, a slash.
const base = process.env.BASE_PATH || '';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: isStatic
			? adapterStatic({
					// Output kept separate from the adapter-node `build/` dir.
					pages: 'build-static',
					assets: 'build-static',
					// No SPA fallback: the curate / comment-only routes are excluded
					// (prerender=false) and simply absent on the public site.
					fallback: undefined,
					// Those excluded routes are non-prerenderable, which is intentional.
					strict: false
				})
			: adapterNode(),
		// Absolute asset/link paths (not relative). The static site deploys at the root
		// of its (sub)domain, so relative paths broke assets on sub-pages — e.g. the
		// licensed font's `./fonts/fonts.css` resolved to `/explore/fonts/…` → 404.
		// `base` still prefixes everything, so a sub-path deploy stays correct.
		paths: { base, relative: false },
		// pollInterval: open tabs check /_app/version.json every 60s; on a version
		// change the next client-side navigation becomes a full-page load, so a
		// deploy can never strand a stale tab on broken in-place navigation.
		version: { name: buildVersion(), pollInterval: 60_000 }
	}
};

export default config;
