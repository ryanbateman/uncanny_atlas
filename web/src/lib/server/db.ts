import { existsSync } from 'node:fs';
import path from 'node:path';
import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import * as schema from './schema';
import { isReadonly } from './cache';

/**
 * Resolve the SQLite path. Mirrors Python's ISTHISAI_DB_PATH env var so the
 * SvelteKit app and the Python pipeline point at the same database. Defaults to
 * <repo-root>/data/isthisai.db (the web/ app runs one level below the repo root).
 */
function resolveDbPath(): string {
	const fromEnv = process.env.ISTHISAI_DB_PATH;
	if (fromEnv) return path.resolve(fromEnv);
	return path.resolve(process.cwd(), '..', 'data', 'isthisai.db');
}

const dbPath = resolveDbPath();
if (!existsSync(dbPath)) {
	throw new Error(
		`SQLite database not found at ${dbPath}. ` +
			`Set ISTHISAI_DB_PATH or run the Python pipeline to create it.`
	);
}

// Python's db.py owns DDL/migrations. In a read-only deployment (ISTHISAI_READONLY)
// we open the file read-only: any stray write then throws at the SQLite layer and
// the file can be mounted :ro. Locally we open read-write but never alter schema.
export const sqlite = new Database(dbPath, { readonly: isReadonly });
// WAL writes to the DB file, so it's only valid on a writable connection.
if (!isReadonly) sqlite.pragma('journal_mode = WAL');
sqlite.pragma('foreign_keys = ON');
sqlite.pragma('busy_timeout = 5000');
// Read-heavy tuning for a large DB: a 64 MB page cache, memory-mapped I/O, and
// in-memory temp storage for the sorts/aggregations the over-time charts run.
sqlite.pragma('cache_size = -65536');
sqlite.pragma('mmap_size = 1073741824');
sqlite.pragma('temp_store = MEMORY');
// Belt-and-braces: refuse writes at the connection level too.
if (isReadonly) sqlite.pragma('query_only = ON');

/**
 * Prepared-statement cache. queries.ts/curate.ts build the same SQL strings on
 * every request; compiling once and reusing the Statement avoids re-parsing SQL
 * per call. Keyed by the exact SQL text. (better-sqlite3 is synchronous, so a
 * cached Statement is never used concurrently.)
 */
const stmtCache = new Map<string, Database.Statement>();
export function prep(sql: string): Database.Statement {
	let s = stmtCache.get(sql);
	if (!s) {
		s = sqlite.prepare(sql);
		stmtCache.set(sql, s);
	}
	return s;
}

export const db = drizzle(sqlite, { schema });
export { dbPath };
