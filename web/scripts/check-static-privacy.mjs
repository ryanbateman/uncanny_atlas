// Post-build privacy tripwire for the static public site.
//
// The static target prerenders against the full local DB; the read-only loads
// are what keep verbatim Reddit comment text and usernames out of the output.
// This script is the belt-and-braces check on the ARTIFACT itself: scan every
// prerendered __data.json for the JSON keys that would only appear if a
// per-comment payload leaked ("body": / "author":), and every prerendered
// .html for the same keys in devalue's unquoted form (body:" / author:") —
// SvelteKit inlines the identical load data into each page's kit.start() call.
// No legitimate read-only payload carries either key.
//
// Limitation: this is a canary, not a proof — a query that aliases a column
// away from body/author would evade it. The svelte.config.js env guard is the
// primary defense; this catches artifact-level regressions.
//
// Runs as part of `npm run build:static`. Exits 1 (failing the build) on a hit.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../build-static', import.meta.url));
// [pattern, applies-to-extension]
const CHECKS = [
	['"body":', '__data.json'],
	['"author":', '__data.json'],
	['body:"', '.html'],
	['author:"', '.html']
];

function* walk(dir) {
	for (const name of readdirSync(dir)) {
		const p = join(dir, name);
		if (statSync(p).isDirectory()) yield* walk(p);
		else if (name.endsWith('__data.json') || name.endsWith('.html')) yield p;
	}
}

let scanned = 0;
const hits = [];
try {
	for (const file of walk(ROOT)) {
		scanned++;
		const text = readFileSync(file, 'utf8');
		for (const [needle, ext] of CHECKS) {
			if (file.endsWith(ext) && text.includes(needle)) hits.push({ file, needle });
		}
	}
} catch (e) {
	console.error(`check-static-privacy: cannot read ${ROOT} — run the static build first (${e.code ?? e.message})`);
	process.exit(1);
}

if (!scanned) {
	console.error('check-static-privacy: no prerendered files found under build-static — wrong cwd?');
	process.exit(1);
}
if (hits.length) {
	console.error('check-static-privacy: FORBIDDEN keys found in prerendered output:');
	for (const h of hits) console.error(`  ${h.needle}  in  ${h.file}`);
	console.error('Verbatim comment data leaked into the public build. Aborting.');
	process.exit(1);
}
console.log(`check-static-privacy: OK — ${scanned} prerendered files scanned, no comment text/usernames.`);
