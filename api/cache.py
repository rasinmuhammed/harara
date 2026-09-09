"""
Tiny in-process TTL cache for Open-Meteo forecast responses.

Open-Meteo's free tier is for non-commercial use and asks callers not to hammer
it; forecasts refresh a few times a day, so a 6-hour TTL keyed by
(lat, lon, date) is ample and keeps a demo well inside the rate limits. The
attribution requirement (CC BY 4.0) is honoured in every /api/plan response and
on the web page.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable, Hashable, TypeVar

T = TypeVar("T")

TTL_SECONDS = 6 * 3600
MAX_ENTRIES = 256


class TTLCache:
    def __init__(self, ttl: float = TTL_SECONDS, maxsize: int = MAX_ENTRIES):
        self.ttl = ttl
        self.maxsize = maxsize
        self._store: "OrderedDict[Hashable, tuple[float, object]]" = OrderedDict()

    def get_or_set(self, key: Hashable, produce: Callable[[], T]) -> T:
        now = time.monotonic()
        hit = self._store.get(key)
        if hit is not None and now - hit[0] < self.ttl:
            self._store.move_to_end(key)
            return hit[1]  # type: ignore[return-value]
        value = produce()
        self._store[key] = (now, value)
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)
        return value

    def clear(self) -> None:
        self._store.clear()


forecast_cache = TTLCache()
