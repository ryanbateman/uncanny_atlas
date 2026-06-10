// The formal media taxonomy (classification rules: src/isthisai/media.py).
// Order is the stable series/legend order — largest-first in this corpus.
export const MEDIA_ORDER = ['image', 'video', 'text', 'other'] as const;
export type MediaType = (typeof MEDIA_ORDER)[number];
