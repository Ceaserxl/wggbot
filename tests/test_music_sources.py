from __future__ import annotations

from pathlib import Path

from modules.musicplayer.sources import MediaResolver


def test_cookiefile_is_only_passed_when_present(settings_factory) -> None:
    settings = settings_factory()
    resolver = MediaResolver(settings)
    assert "cookiefile" not in resolver._ydl_options(playlist=False)
    Path(settings.ytdlp_cookie_file).write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    options = resolver._ydl_options(playlist=True, playlist_limit=12)
    assert options["cookiefile"] == str(settings.ytdlp_cookie_file)
    assert options["playlistend"] == 12
    assert options["extract_flat"] == "in_playlist"


def test_flat_youtube_entry_becomes_canonical_track(settings_factory) -> None:
    track = MediaResolver._track_from_info(
        {
            "id": "abc123",
            "title": "Song",
            "uploader": "Artist",
            "extractor_key": "Youtube",
            "duration": 125,
        },
        requester_id=7,
        requester_mention="<@7>",
    )
    assert track.webpage_url == "https://www.youtube.com/watch?v=abc123"
    assert track.label == "Song — Artist"
    assert track.duration_label == "2:05"


def test_spotify_detection_is_host_specific(settings_factory) -> None:
    resolver = MediaResolver(settings_factory())
    assert resolver._is_spotify_url("https://open.spotify.com/track/123")
    assert not resolver._is_spotify_url("https://example.com/open.spotify.com/track/123")
    assert not resolver._is_spotify_url("some search text")
