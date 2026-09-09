"""
Fixed-window per-IP rate limit for /api/chat. In-process, which is enough for
a single-instance demo (the Render free tier runs one instance). Not a
security control, just politeness toward the model provider and Open-Meteo.
"""

from __future__ import annotations

import time

WINDOW_SECONDS = 300
MAX_REQUESTS = 20


class RateLimiter:
    def __init__(self, window: int = WINDOW_SECONDS, limit: int = MAX_REQUESTS):
        self.window = window
        self.limit = limit
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str) -> tuple[bool, int]:
        """(allowed, retry_after_seconds). retry_after is 0 when allowed."""
        now = time.monotonic()
        cutoff = now - self.window
        hits = [t for t in self._hits.get(key, ()) if t > cutoff]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False, int(self.window - (now - hits[0])) + 1
        hits.append(now)
        self._hits[key] = hits
        # opportunistic cleanup so the dict does not grow without bound
        if len(self._hits) > 4096:
            self._hits = {k: v for k, v in self._hits.items()
                          if v and v[-1] > cutoff}
        return True, 0

    def reset(self) -> None:
        self._hits.clear()


chat_limiter = RateLimiter()
