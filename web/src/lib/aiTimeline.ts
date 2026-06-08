// Major public AI image/video releases + general milestones, shown as vertical
// markers on the over-time charts for context. Dates are public-release dates.
// `kind` is the output modality (image / video / text); `release` is how it
// shipped (open weights, public, research preview, ...). Edit freely. Sources
// are in the commit / PR that added these.
export type AiEvent = {
	date: string;
	label: string;
	kind: 'image' | 'video' | 'text';
	release: string;
};

// `release` is a single word, chosen for accuracy:
//   open    — open weights, freely downloadable (Stable Diffusion, FLUX.1)
//   preview — shipped as a research/preview build, not stable (ChatGPT, Nano Banana)
//   alpha   — early/alpha iteration at launch (Midjourney v5)
//   paid    — gated behind a paid tier and/or region-locked at launch (Sora, Veo 3)
//   staged  — phased rollout, paid-tier first then wider (GPT-4o images)
export const AI_EVENTS: AiEvent[] = [
	{ date: '2022-08-22', label: 'Stable Diffusion', kind: 'image', release: 'open' },
	{ date: '2022-11-30', label: 'ChatGPT', kind: 'text', release: 'preview' },
	{ date: '2023-03-15', label: 'Midjourney v5', kind: 'image', release: 'alpha' },
	{ date: '2024-08-01', label: 'FLUX.1', kind: 'image', release: 'open' },
	{ date: '2024-12-09', label: 'Sora', kind: 'video', release: 'paid' },
	{ date: '2025-03-25', label: 'GPT-4o images', kind: 'image', release: 'staged' },
	{ date: '2025-05-20', label: 'Veo 3', kind: 'video', release: 'paid' },
	{ date: '2025-08-26', label: 'Nano Banana', kind: 'image', release: 'preview' }
];
