#!/usr/bin/env sh
# Fetch the aggregate-only deploy DB from a PRIVATE location into place.
#
# The DB is never committed or attached to the public repo (see plan Part C). It
# lives in private object storage (S3/R2) or on a host volume; this script pulls
# it via a non-public URL kept in env. Run it before launching the server, or
# from a container entrypoint.
#
#   ISTHISAI_DB_URL    required — private/presigned URL to isthisai-deploy.db
#   ISTHISAI_DB_PATH   target path (default: /data/isthisai.db)
set -eu

URL="${ISTHISAI_DB_URL:?Set ISTHISAI_DB_URL to the private deploy-DB location}"
DEST="${ISTHISAI_DB_PATH:-/data/isthisai.db}"

mkdir -p "$(dirname "$DEST")"
echo "Fetching deploy DB -> $DEST"
curl -fSL --retry 3 -o "$DEST" "$URL"
echo "Done ($(du -h "$DEST" 2>/dev/null | cut -f1))."
