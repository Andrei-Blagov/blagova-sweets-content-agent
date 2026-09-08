"""Simple in-memory login rate limiter."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 600) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            return len(self._failures[key]) >= self.max_attempts

    def register_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._failures[key].append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def _prune(self, key: str, now: float) -> None:
        bucket = self._failures[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if not bucket and key in self._failures:
            del self._failures[key]
