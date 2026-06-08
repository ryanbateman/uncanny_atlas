/** Thousands-separated integer formatting, locale-stable across server/client. */
export const n = (v: number | null | undefined): string => (v ?? 0).toLocaleString('en-US');
