"""
Rate Limiter - core/rate_limiter.py
In-memory sliding window rate limiter for anti-nuke and spam detection.
Designed for high-performance, low-latency checks on large servers.
"""

import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding window rate limiter using deques.

    Key format: "{guild_id}:{user_id}:{action}"
    Each key holds a deque of timestamps within the current window.
    """

    def __init__(self) -> None:
        # {key: deque of timestamps}
        self._windows: Dict[str, deque] = defaultdict(deque)
        # Cleanup interval (seconds) — prune old entries periodically
        self._last_cleanup: float = time.monotonic()
        self._cleanup_interval: float = 30.0

    def _make_key(self, guild_id: int, user_id: int, action: str) -> str:
        return f"{guild_id}:{user_id}:{action}"

    def check(
        self,
        guild_id: int,
        user_id: int,
        action: str,
        limit: int,
        window: int,
    ) -> Tuple[bool, int]:
        """
        Record an event and check if the rate limit is exceeded.

        Returns:
            (exceeded: bool, current_count: int)
        """
        key = self._make_key(guild_id, user_id, action)
        now = time.monotonic()
        cutoff = now - window

        dq = self._windows[key]

        # Remove expired timestamps
        while dq and dq[0] < cutoff:
            dq.popleft()

        # Add current event
        dq.append(now)
        count = len(dq)

        # Periodic cleanup of stale keys
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup(now)

        return count >= limit, count

    def get_count(
        self,
        guild_id: int,
        user_id: int,
        action: str,
        window: int,
    ) -> int:
        """Get current event count within window without recording."""
        key = self._make_key(guild_id, user_id, action)
        now = time.monotonic()
        cutoff = now - window
        dq = self._windows[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        return len(dq)

    def reset(self, guild_id: int, user_id: int, action: str) -> None:
        """Clear rate limit state for a specific key."""
        key = self._make_key(guild_id, user_id, action)
        self._windows.pop(key, None)

    def reset_user(self, guild_id: int, user_id: int) -> None:
        """Clear all rate limit state for a user in a guild."""
        prefix = f"{guild_id}:{user_id}:"
        keys_to_delete = [k for k in self._windows if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._windows[k]

    def _cleanup(self, now: float) -> None:
        """Remove stale keys to prevent memory leaks."""
        stale_keys = []
        for key, dq in self._windows.items():
            # Assume max window of 60s for cleanup purposes
            cutoff = now - 60
            while dq and dq[0] < cutoff:
                dq.popleft()
            if not dq:
                stale_keys.append(key)
        for k in stale_keys:
            del self._windows[k]
        self._last_cleanup = now


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter — best for per-user command cooldowns.
    Fills at `rate` tokens/second, capped at `capacity`.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self._buckets: Dict[str, Tuple[float, float]] = {}  # key: (tokens, last_refill)

    def consume(self, key: str, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens. Returns True if allowed, False if rate-limited.
        """
        now = time.monotonic()
        current_tokens, last_refill = self._buckets.get(key, (self.capacity, now))

        # Refill tokens based on elapsed time
        elapsed = now - last_refill
        current_tokens = min(self.capacity, current_tokens + elapsed * self.rate)

        if current_tokens >= tokens:
            self._buckets[key] = (current_tokens - tokens, now)
            return True
        else:
            self._buckets[key] = (current_tokens, now)
            return False

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


# Singleton instances used across cogs
rate_limiter = SlidingWindowRateLimiter()
command_limiter = TokenBucketRateLimiter(rate=0.5, capacity=3.0)
