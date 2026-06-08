// Curate mutates the DB through form actions, so it can never be a static page.
// prerender=false excludes the whole /curate subtree from the static public build
// (it's already hidden + POST-guarded in read-only mode); the adapter-node build is
// unaffected (SSR is its default).
export const prerender = false;
