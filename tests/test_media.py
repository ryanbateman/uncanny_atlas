import pytest

from isthisai.media import MEDIA_TYPES, classify_media_type


@pytest.mark.parametrize(
    ("is_video", "is_self", "url", "expected"),
    [
        # text: is_self wins even when the url is the reddit permalink
        (0, 1, "https://www.reddit.com/r/isthisAI/comments/abc/some_title/", "text"),
        (None, 1, None, "text"),
        # video: the Reddit flag
        (1, 0, None, "video"),
        (1, 0, "https://v.redd.it/abc", "video"),
        # video: unflagged v.redd.it (crossposts) — the flag misses these
        (0, 0, "https://v.redd.it/xyz123", "video"),
        # video: external hosts
        (0, 0, "https://www.youtube.com/watch?v=abc", "video"),
        (0, 0, "https://youtu.be/abc", "video"),
        (0, 0, "https://streamable.com/abc", "video"),
        (0, 0, "https://www.redgifs.com/watch/abc", "video"),
        (0, 0, "https://www.tiktok.com/@user/video/123", "video"),
        (0, 0, "https://clips.twitch.tv/abc", "video"),
        # video: extension beats image host (imgur .gifv is a video format)
        (0, 0, "https://i.imgur.com/abc.gifv", "video"),
        # video: case-insensitive extension + query-string suffix
        (0, 0, "https://example.com/clip.MP4?source=share", "video"),
        (0, 0, "https://example.com/a.webm", "video"),
        # image: reddit galleries fold into image
        (0, 0, "https://www.reddit.com/gallery/abc", "image"),
        # image: hosts
        (0, 0, "https://i.redd.it/abc.jpeg", "image"),
        (0, 0, "https://preview.redd.it/abc?width=640", "image"),
        (0, 0, "https://imgur.com/a/abc", "image"),
        # image: extensions, case + query suffix
        (0, 0, "https://example.com/photo.JPG", "image"),
        (0, 0, "https://cdn.example.com/x.webp?w=640", "image"),
        # other: socials (unresolvable from URL), articles, permalinks, empties
        (0, 0, "https://www.instagram.com/p/abc/", "other"),
        (0, 0, "https://www.facebook.com/reel/123", "other"),
        (0, 0, "https://www.example.com/article-about-ai", "other"),
        (0, 0, "https://www.reddit.com/r/x/comments/abc/title/", "other"),
        (0, 0, None, "other"),
        (0, 0, "", "other"),
        (None, None, None, "other"),
    ],
)
def test_classify_media_type(is_video, is_self, url, expected):
    assert classify_media_type(is_video, is_self, url) == expected


@pytest.mark.parametrize(
    ("is_video", "is_self", "url"),
    [
        (0, 0, "https://weird.host/whatever"),
        (1, 1, "https://v.redd.it/x"),  # contradictory flags still classify
        (None, None, "not even a url"),
    ],
)
def test_classifier_is_total(is_video, is_self, url):
    # Whatever the input, the result is always a member of the taxonomy.
    assert classify_media_type(is_video, is_self, url) in MEDIA_TYPES
