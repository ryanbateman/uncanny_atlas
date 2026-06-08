# Uncanny Atlas — read-only public site (SvelteKit adapter-node).
#
# The image contains ONLY code. No data is baked in: provide the aggregate-only
# snapshot (built offline by scripts/build_deploy_db.py) at runtime via a mounted
# read-only volume or scripts/fetch_db.sh, and point ISTHISAI_DB_PATH at it.
#
# Build context is the repo root:   docker build -t uncanny-atlas .
# Run (mount the DB read-only):
#   docker run -p 3000:3000 -v /host/isthisai-deploy.db:/data/isthisai.db:ro uncanny-atlas

# ---- build stage -----------------------------------------------------------
FROM node:20-slim AS build
WORKDIR /app/web
# Toolchain for the better-sqlite3 native addon.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends python3 make g++ \
	&& rm -rf /var/lib/apt/lists/*
# Install deps against the committed lockfile first (better layer caching).
COPY web/package.json web/package-lock.json ./
RUN npm ci
# Build the app, then drop dev dependencies (keeps the native better-sqlite3 addon,
# which is a runtime dependency, already compiled for this base image).
COPY web/ ./
RUN npm run build && npm prune --omit=dev

# ---- runtime stage ---------------------------------------------------------
FROM node:20-slim AS runtime
WORKDIR /app/web
ENV NODE_ENV=production \
	ISTHISAI_READONLY=1 \
	ISTHISAI_DB_PATH=/data/isthisai.db \
	PORT=3000
# Built server + production node_modules (native addon matches this same base).
COPY --from=build /app/web/build ./build
COPY --from=build /app/web/node_modules ./node_modules
COPY --from=build /app/web/package.json ./package.json
EXPOSE 3000
# The app opens ISTHISAI_DB_PATH read-only; mount the aggregate-only DB there.
CMD ["node", "build"]
