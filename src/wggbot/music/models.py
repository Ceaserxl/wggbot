from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Track:
    title: str
    webpage_url: str
    requester_id: int
    requester_mention: str
    artist: str = "Unknown artist"
    duration: int | None = None
    source: str = "unknown"
    thumbnail: str | None = None
    original_url: str | None = None

    @property
    def label(self) -> str:
        return f"{self.title} — {self.artist}" if self.artist else self.title

    @property
    def duration_label(self) -> str:
        if self.duration is None:
            return "LIVE" if "live" in self.title.lower() else "—:—"
        minutes, seconds = divmod(max(0, self.duration), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

    @property
    def link_url(self) -> str | None:
        for candidate in (self.webpage_url, self.original_url):
            if candidate and candidate.startswith(("https://", "http://")):
                return candidate
        return None
