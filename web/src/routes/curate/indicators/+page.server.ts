import type { Actions, PageServerLoad } from './$types';
import { fail } from '@sveltejs/kit';
import * as curate from '$lib/server/curate';

export const load: PageServerLoad = ({ url }) => {
	const mode = (url.searchParams.get('mode') as curate.Mode) || 'all';
	const search = url.searchParams.get('search') || '';
	const sort = url.searchParams.get('sort') || 'freq_desc';
	const limit = Number(url.searchParams.get('limit')) || 50;
	const offset = Math.max(0, Number(url.searchParams.get('offset')) || 0);
	// Default to showing reviewed rows too; only hide when explicitly asked.
	const showReviewed = url.searchParams.get('reviewed') !== 'hide';
	return {
		mode,
		search,
		sort,
		limit,
		offset,
		showReviewed,
		categories: curate.CATEGORIES,
		stats: curate.indicatorStats(),
		seedsTotal: curate.taxonomyTotal(),
		stopList: curate.stopIndicators(),
		pending: curate.pendingExpansion(),
		rows: curate.listIndicators({ mode, search, sort, limit, offset, showReviewed }),
		total: curate.countIndicators({ mode, search, showReviewed })
	};
};

const isCat = (c: string) => (curate.CATEGORIES as readonly string[]).includes(c);

export const actions: Actions = {
	// Set a category on every comment with this phrase (cascade + taxonomy mirror).
	assign: async ({ request }) => {
		const f = await request.formData();
		const indicator = String(f.get('indicator') ?? '');
		const category = String(f.get('category') ?? '');
		if (!indicator || !isCat(category)) return fail(400, { message: 'Invalid indicator or category.' });
		const n = curate.assignCategory(indicator, category);
		return {
			message:
				n > 1
					? `Set “${indicator}” → ${category} (cascaded to ${n} merged phrases).`
					: `Set “${indicator}” → ${category}.`
		};
	},
	// Bulk: set every indicator matching the current search to a category.
	batch: async ({ request }) => {
		const f = await request.formData();
		const substring = String(f.get('substring') ?? '').trim();
		const category = String(f.get('category') ?? '');
		const mode = String(f.get('mode') ?? 'all') as curate.Mode;
		if (!substring || !isCat(category)) return fail(400, { message: 'Provide a search and a category.' });
		const changed = curate.assignBySubstring(substring, category, mode);
		return {
			message: `Set ${changed} rows for “${substring}” → ${category} (merge groups kept whole).`
		};
	},
	reset: async ({ request }) => {
		const f = await request.formData();
		const substring = String(f.get('substring') ?? '').trim();
		const changed = curate.resetNoise(substring || undefined);
		return { message: `Reset ${changed} Noise rows to uncategorised.` };
	},
	// Add a brand-new expansion seed (a phrase that may not be in the data yet).
	addSeed: async ({ request }) => {
		const f = await request.formData();
		const pattern = String(f.get('pattern') ?? '').trim();
		const category = String(f.get('category') ?? '');
		if (!pattern || !isCat(category)) return fail(400, { message: 'Provide an indicator and a category.' });
		if (category === 'Noise')
			return fail(400, { message: 'A seed must be a real indicator — Noise indicators are never expanded.' });
		const ok = curate.addTaxonomy(pattern, category, null);
		return {
			message: ok
				? `Added “${pattern}” as a seed — run embed indicators + semantic for it to gather comments.`
				: `“${pattern}” is already a seed.`
		};
	},
	// Toggle whether an existing indicator is an expansion seed.
	toggleSeed: async ({ request }) => {
		const f = await request.formData();
		const indicator = String(f.get('indicator') ?? '');
		if (!indicator) return fail(400, { message: 'Missing indicator.' });
		if (f.get('on') === 'true') {
			const category = String(f.get('category') ?? '');
			// Noise and Seed are mutually exclusive — a Noise phrase isn't expanded.
			if (category === 'Noise')
				return fail(400, { message: 'Noise indicators aren’t expanded — clear the Noise category before seeding.' });
			curate.addTaxonomy(indicator, isCat(category) ? category : 'Meta', null);
			return { message: `“${indicator}” is now a seed — run embed indicators + semantic to expand it.` };
		}
		curate.deleteTaxonomy(indicator);
		return { message: `Removed “${indicator}” as a seed. Existing matches stay — Noise it to drop them from the charts.` };
	}
};
