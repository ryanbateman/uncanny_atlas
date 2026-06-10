import type { Actions, PageServerLoad } from './$types';
import { fail } from '@sveltejs/kit';
import * as curate from '$lib/server/curate';

// Read-only discovery feed over a stored snapshot. The hooks.server.ts POST
// guard and curate/+layout.ts prerender=false cover this route like the rest
// of /curate — no extra wiring.
export const load: PageServerLoad = () => ({
	snapshot: curate.loadEmergingSnapshot(),
	embeddingsReady: curate.hasPhraseEmbeddings()
});

export const actions: Actions = {
	// Compute-and-store, never per-load: clustering is seconds of CPU (the page
	// states as much on the button). Stale is fine — refreshed monthly.
	recompute: async ({ request }) => {
		const f = await request.formData();
		const t = Number(f.get('threshold'));
		const threshold = Number.isFinite(t) && t >= 0.5 && t <= 0.95 ? t : 0.7;
		if (!curate.hasPhraseEmbeddings()) {
			return fail(400, {
				message:
					'No phrase embeddings yet — run `isthisai-embed categorize` (or `ground`) once to populate them.'
			});
		}
		const snap = curate.computeEmergingClusters(threshold);
		curate.saveEmergingSnapshot(snap);
		return {
			message: `Found ${snap.clusters.length} clusters from the top ${snap.poolSize} of ${snap.eligible} uncategorised phrases.`
		};
	}
};
