import { sqliteTable, text, integer, real, blob, primaryKey } from 'drizzle-orm/sqlite-core';

/**
 * Drizzle definitions mirroring the schema owned by Python's src/isthisai/db.py.
 * These are for typed read/write only — we never run Drizzle migrations against
 * this database. Keep in sync with db.py if the Python schema changes.
 */

export const submissions = sqliteTable('submissions', {
	id: text('id').primaryKey(),
	title: text('title'),
	author: text('author'),
	createdUtc: real('created_utc').notNull(),
	score: integer('score'),
	numComments: integer('num_comments'),
	upvoteRatio: real('upvote_ratio'),
	linkFlairText: text('link_flair_text'),
	isVideo: integer('is_video'),
	isSelf: integer('is_self'),
	url: text('url'),
	selftext: text('selftext'),
	permalink: text('permalink'),
	retrievedUtc: real('retrieved_utc'),
	subreddit: text('subreddit').notNull().default('isthisAI'),
	// Formal media classification (video|image|text|other) — src/isthisai/media.py
	mediaType: text('media_type')
});

export const comments = sqliteTable('comments', {
	id: text('id').primaryKey(),
	linkId: text('link_id').notNull(),
	author: text('author'),
	body: text('body'),
	createdUtc: real('created_utc').notNull(),
	score: integer('score'),
	parentId: text('parent_id'),
	retrievedUtc: real('retrieved_utc'),
	subreddit: text('subreddit').notNull().default('isthisAI')
});

export const commentIndicators = sqliteTable(
	'comment_indicators',
	{
		commentId: text('comment_id').notNull(),
		indicator: text('indicator').notNull(),
		category: text('category'),
		batchId: text('batch_id').notNull(),
		canonicalIndicator: text('canonical_indicator'),
		reviewed: integer('reviewed').default(0)
	},
	(t) => ({ pk: primaryKey({ columns: [t.commentId, t.indicator] }) })
);

export const indicatorTaxonomy = sqliteTable('indicator_taxonomy', {
	indicatorPattern: text('indicator_pattern').primaryKey(),
	category: text('category').notNull(),
	subcategory: text('subcategory')
});

export const indicatorEmbeddings = sqliteTable('indicator_embeddings', {
	indicatorPattern: text('indicator_pattern').primaryKey(),
	embedding: blob('embedding').notNull(),
	model: text('model').notNull()
});

export const indicatorAliases = sqliteTable('indicator_aliases', {
	alias: text('alias').primaryKey(),
	canonical: text('canonical').notNull()
});

export const extractionRuns = sqliteTable('extraction_runs', {
	batchId: text('batch_id').primaryKey(),
	model: text('model').notNull(),
	startedAt: text('started_at'),
	completedAt: text('completed_at'),
	sampleSize: integer('sample_size'),
	commentsProcessed: integer('comments_processed')
});
