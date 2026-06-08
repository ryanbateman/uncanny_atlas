# Fetch the aggregate-only deploy DB from a PRIVATE location into place.
#
# The DB is never committed or attached to the public repo (see plan Part C). It
# lives in private object storage (S3/R2) or on a host volume; this script pulls
# it via a non-public URL kept in env.
#
#   $env:ISTHISAI_DB_URL    required — private/presigned URL to isthisai-deploy.db
#   $env:ISTHISAI_DB_PATH   target path (default: data/isthisai.db)
$ErrorActionPreference = 'Stop'

$url = $env:ISTHISAI_DB_URL
if (-not $url) { throw 'Set ISTHISAI_DB_URL to the private deploy-DB location' }
$dest = if ($env:ISTHISAI_DB_PATH) { $env:ISTHISAI_DB_PATH } else { 'data/isthisai.db' }

$dir = Split-Path -Parent $dest
if ($dir) { New-Item -ItemType Directory -Force $dir | Out-Null }
Write-Host "Fetching deploy DB -> $dest"
Invoke-WebRequest -Uri $url -OutFile $dest
Write-Host ("Done ({0:N0} MB)." -f ((Get-Item $dest).Length / 1MB))
