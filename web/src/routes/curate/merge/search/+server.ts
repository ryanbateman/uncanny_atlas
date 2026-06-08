import type { RequestHandler } from './$types';
import { json } from '@sveltejs/kit';
import * as curate from '$lib/server/curate';

// Not part of the static public build; curation is disabled in read-only mode.
export const prerender = false;

// Light JSON endpoint that powers the client-side merge builder: candidate phrases
// for a search + the combined distinct-comment count for a phrase set. Keeps the
// expensive cluster suggestion off the per-keystroke path (it stays on the page load).
export const GET: RequestHandler = ({ url, locals }) => {
	if (locals.readonly) return json({ candidates: [], impact: 0 });
	const q = (url.searchParams.get('q') ?? '').trim();
	const phrases = url.searchParams.getAll('p').map((s) => s.trim()).filter(Boolean);
	return json({
		candidates: q ? curate.searchMergeCandidates(q, 30) : [],
		impact: curate.mergeImpact(phrases).comments
	});
};
