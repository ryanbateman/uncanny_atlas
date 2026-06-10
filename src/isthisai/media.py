"""Submission media-type classification.

Single source of truth for the 4-way media taxonomy stored in
submissions.media_type and used by every chart/table that filters by medium:

    'video' | 'image' | 'text' | 'other'

Reddit's own flags are not enough: is_video marks only Reddit-HOSTED video, so
externally-linked video (YouTube, unflagged v.redd.it crossposts, streamable,
.mp4 links — ~2,500 posts, +48% over the flagged count in the 2026-06 corpus)
would otherwise be lumped in with images. Hence flags PLUS the link's host and
file extension.

Precedence (deliberate, validated against the full 2026-06 corpus):
  1. text  — is_self=1. A self post is a text post even if its body links media.
  2. video — is_video=1 (Reddit-hosted) OR a known video host OR a video file
             extension. Runs BEFORE image so e.g. imgur .gifv (a video format
             on an image host) classifies as video.
  3. image — Reddit galleries fold into image (a gallery is several images),
             plus image hosts and image file extensions.
  4. other — everything else: instagram/facebook links (unresolvable from the
             URL alone), article links, crossposts/permalinks, empty url.

Changing these lists? Re-classify existing rows with `isthisai-enrich
post-types` (no schema bump needed).
"""

from __future__ import annotations

# Substring matches against the lowercased full URL. Hostnames kept bare
# ('imgur', 'tiktok') where subdomains vary (i.imgur.com, m.tiktok.com).
VIDEO_HOSTS = (
    "v.redd.it",
    "youtube.com",
    "youtu.be",
    "streamable",
    "redgifs",
    "gfycat",
    "tiktok",
    "twitch",
)
VIDEO_EXTENSIONS = (".mp4", ".gifv", ".webm")
IMAGE_HOSTS = ("reddit.com/gallery", "i.redd.it", "preview.redd.it", "imgur")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")

MEDIA_TYPES = ("video", "image", "text", "other")


def _has_extension(url: str, extensions: tuple[str, ...]) -> bool:
    # Strip the query string so '.mp4?source=share' still matches. ('#'
    # fragments are vanishingly rare in Reddit post URLs; not handled.)
    return url.split("?", 1)[0].endswith(extensions)


def classify_media_type(
    is_video: int | bool | None, is_self: int | bool | None, url: str | None
) -> str:
    """Classify one submission. Total: always returns one of MEDIA_TYPES."""
    if is_self:
        return "text"
    u = (url or "").lower()
    if is_video or any(h in u for h in VIDEO_HOSTS) or _has_extension(u, VIDEO_EXTENSIONS):
        return "video"
    if any(h in u for h in IMAGE_HOSTS) or _has_extension(u, IMAGE_EXTENSIONS):
        return "image"
    return "other"
