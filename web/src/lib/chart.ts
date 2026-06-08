import type * as PlotNS from '@observablehq/plot';

// Shared chart styling so every Observable Plot looks the same.
//
// Palette: "Set2" — the classic qualitative palette from R's RColorBrewer
// (Brewer 2003). Colourblind-friendly, soft mid-tones that read cleanly on a
// light background. It carries 8 distinct hues; the default Indicators view
// hides Noise and shows exactly 8 taxonomy categories, so there's no recycling.
export const CATEGORY_SCHEME = 'Set2';

// The Set2 hex ramp, so a hand-rolled legend (rendered below a chart) can match
// the colours Plot assigns from the `Set2` scheme exactly.
export const SET2 = [
	'#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3',
	'#a6d854', '#ffd92f', '#e5c494', '#b3b3b3'
];

// Single-series bar fills, drawn from the same Set2 palette so one-off charts
// stay in family with the categorical ones.
export const BAR_BLUE = '#8da0cb';
export const BAR_TEAL = '#66c2a5';
export const BAR_ORANGE = '#fc8d62';

// Light theme: white plot area, dark ink for axes/labels, so the figures read
// as clean inset panels rather than dark-on-dark.
export const CHART_STYLE = { background: '#fffdf8', color: '#262019' };

// 20-colour qualitative range (Tableau 20) for many-series line charts where the
// 8-hue Set2 would recycle too quickly. Colours still repeat past 20 lines, so
// rely on the tooltip/legend to disambiguate.
export const LINE_PALETTE = [
	'#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
	'#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
	'#a0cbe8', '#ffbe7d', '#ff9d9a', '#8cd17d', '#b6992d',
	'#86bcb6', '#d37295', '#fabfd2', '#d4a6c8', '#79706e'
];

// Muted grid lines that sit quietly on the white background.
export const GRID_COLOR = '#e7ddc9';

// Axis spines: a horizontal (bottom) and vertical (left) line. Implemented as
// single-sided frames so they don't disturb tick/label/grid configuration.
export function spines(P: typeof PlotNS) {
	return [
		P.frame({ anchor: 'left', stroke: '#b6a98f' }),
		P.frame({ anchor: 'bottom', stroke: '#b6a98f' })
	];
}

// Time-series rendering mode, shared by every over-time chart.
//   line    — one line per series
//   stacked — stacked area (absolute)
//   percent — 100% stacked area (share of total; only meaningful for whole-decompositions)
export type SeriesMode = 'line' | 'stacked' | 'percent';

/** The mark for a multi-series time chart, switched by mode (line vs area). */
export function seriesMark(
	P: typeof PlotNS,
	data: unknown[],
	opts: { x: string; y: string; series: string; mode: SeriesMode }
) {
	const { x, y, series, mode } = opts;
	const d = data as Parameters<typeof P.lineY>[0];
	if (mode === 'line') return P.lineY(d, { x, y, stroke: series, tip: true });
	// In 100%-stacked (percent) mode the y channel is the normalized share, so show
	// it in the hover tooltip as a percentage (e.g. 23.4%) rather than a raw decimal.
	const tip = mode === 'percent' ? { format: { y: '.1%' } } : true;
	return P.areaY(d, { x, y, fill: series, offset: mode === 'percent' ? 'normalize' : null, tip });
}

/** The y-scale config for a time chart, adding the % axis in percent mode. */
export function seriesY(mode: SeriesMode, label: string) {
	// labelAnchor 'center' rotates the axis label and centres it along the axis
	// (vs Plot's default top-of-axis placement); labelArrow off for a clean read.
	const anchor = { labelAnchor: 'center' as const, labelArrow: 'none' as const };
	return mode === 'percent'
		? { grid: true, label: `share of ${label}`, tickFormat: '.0%', ...anchor }
		: { grid: true, label, ...anchor };
}

// ---- continuous time axis (shared by the over-time charts) --------------
//
// A two-tier x-axis on a UTC time scale: bold YEAR ticks (major) plus lighter
// granularity ticks (minor), with matching vertical grid lines so the panels
// read as graph paper. Use `x: { type: 'utc', domain, axis: null }` on the
// plot and add these marks; `axis: null` suppresses Plot's implicit single-tier
// axis so only these show.

/** Plot interval name for the minor (granularity) ticks. */
export function minorInterval(granularity: string): string {
	if (granularity === 'month') return 'month';
	if (granularity === 'day') return 'day';
	return 'monday'; // week → ISO Mondays, matching the bucketed data points
}

/** Vertical grid lines: faint minor (granularity) + stronger major (year). */
export function timeGrid(P: typeof PlotNS, granularity: string) {
	return [
		P.gridX({ ticks: minorInterval(granularity), stroke: GRID_COLOR, strokeOpacity: 0.55 }),
		P.gridX({ ticks: 'year', stroke: '#c9bda4', strokeWidth: 1.2 })
	];
}

/** Tick marks + labels: unlabeled minor ticks + bold year labels. */
export function timeTicks(P: typeof PlotNS, granularity: string) {
	return [
		P.axisX({ ticks: minorInterval(granularity), tickFormat: () => '', tickSize: 3, stroke: '#b6a98f' }),
		P.axisX({
			ticks: 'year',
			tickFormat: (d: Date) => String(d.getUTCFullYear()),
			tickSize: 8,
			fontSize: 11,
			fontWeight: 700
		})
	];
}

/**
 * Corpus milestone markers (first submission, first comment collected): text
 * only — no rule line. A bold label hangs into the BOTTOM margin (below the axis,
 * reading bottom-to-top) with the exact date as a smaller muted sub-label beside
 * it, mirroring the release markers' title/sub-title pairing. Kept clear of the
 * AI-release labels crowded into the top margin. Entries with a null date are
 * dropped; an empty input renders nothing. Charts using this need enough
 * marginBottom to fit the rotated labels.
 */
export function milestoneMarks(
	P: typeof PlotNS,
	milestones: { date: string | null; label: string }[]
) {
	const data = milestones
		.filter((m): m is { date: string; label: string } => !!m.date)
		.map((m) => ({ dt: new Date(m.date + 'T00:00:00Z'), label: m.label, date: m.date }));
	if (!data.length) return [];
	const title = (d: { label: string; date: string }) => `${d.label}\n${d.date}`;
	// rotate -90 (same reading direction as the release labels: bottom-to-top);
	// textAnchor 'end' keeps the text hanging BELOW the axis rather than rising into
	// the plot, with dy pushing it clear of the year tick labels. For this rotation
	// a larger dx is the "next line below", so the date sits just under the label.
	const common = { x: 'dt', title, frameAnchor: 'bottom' as const, rotate: -90, textAnchor: 'end' as const, dy: 8 };
	return [
		P.text(data, { ...common, text: 'label', dx: 3, fontSize: 9.5, fontWeight: 700, fill: '#15181f' }),
		P.text(data, { ...common, text: 'date', dx: 14, fontSize: 8, fill: '#4b5563' })
	];
}

type Marker = { dt: Date; label: string; kind: string; release: string; date: string };

/**
 * Vertical AI-release event markers: a red line, a bold red product label and a
 * smaller modality (kind) tag in the top margin, plus a hover tooltip carrying
 * the full type + release + date.
 */
export function eventMarks(P: typeof PlotNS, markers: Marker[]) {
	const title = (d: Marker) => `${d.label}\n${d.kind} model · ${d.release} release\n${d.date}`;
	return [
		P.ruleX(markers, {
			x: 'dt',
			stroke: '#dc2626',
			strokeWidth: 1,
			strokeOpacity: 0.7,
			strokeDasharray: '2 3',
			title
		}),
		P.text(markers, {
			x: 'dt',
			text: 'label',
			title,
			frameAnchor: 'top',
			rotate: -90,
			textAnchor: 'start',
			dx: 2,
			dy: -12,
			fontSize: 9.5,
			fontWeight: 700,
			fill: '#15181f'
		}),
		P.text(markers, {
			x: 'dt',
			text: (d: Marker) => `${d.kind} · ${d.release}`,
			title,
			frameAnchor: 'top',
			rotate: -90,
			textAnchor: 'start',
			dx: 13,
			dy: -12,
			fontSize: 8,
			fill: '#4b5563'
		})
	];
}
