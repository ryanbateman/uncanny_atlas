import type { Actions, PageServerLoad } from './$types';
import { fail } from '@sveltejs/kit';
import * as curate from '$lib/server/curate';

const isCat = (c: string) => (curate.CATEGORIES as readonly string[]).includes(c);

export const load: PageServerLoad = ({ url }) => {
	const threshold = Number(url.searchParams.get('threshold')) || 0.7;
	const merges = curate.listMerges();
	return {
		threshold,
		clusters: curate.clusterSuggestions(threshold),
		merges,
		categories: curate.CATEGORIES,
		// Existing canonical names, so a cluster can be folded into one that
		// already exists (autocomplete) rather than only typed free-hand.
		canonicals: merges.map((m) => m.canonical).sort((a, b) => a.localeCompare(b)),
		// Optional builder prefill (from a cluster's "open in builder" link, or an
		// active-merge "+ add" link). The builder itself runs client-side.
		prefillSel: [...new Set(url.searchParams.getAll('sel').map((s) => s.trim()).filter(Boolean))],
		prefillInto: url.searchParams.get('into')
	};
};

export const actions: Actions = {
	merge: async ({ request }) => {
		const form = await request.formData();
		const canonical = String(form.get('canonical') ?? '').trim();
		const aliases = form.getAll('aliases').map(String).filter(Boolean);
		const category = String(form.get('category') ?? '');
		if (!canonical || aliases.length === 0)
			return fail(400, { message: 'Pick a canonical name and at least one member.' });
		// A merge is one indicator, so it must carry one explicit category (or Noise).
		if (!isCat(category))
			return fail(400, { message: 'Choose a category (or Noise) for the merged indicator.' });
		curate.merge(canonical, aliases, category);
		return { message: `Merged ${aliases.length} phrase(s) into “${canonical}” → ${category}.` };
	},
	unmerge: async ({ request }) => {
		const form = await request.formData();
		const canonical = String(form.get('canonical') ?? '');
		if (!canonical) return fail(400, { message: 'Missing canonical.' });
		curate.unmerge(canonical);
		return { message: `Unmerged “${canonical}”.` };
	}
};
