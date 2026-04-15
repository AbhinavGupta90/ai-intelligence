"""
Rate limiter — token-bucket per source to avoid API bans.
"""

import time
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict

from src.logger import log


@dataclass
class Bucket:
    """Token bucket for a single source."""
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    async def acquire(self, tokens: float = 1.0):
        """Wait until enough tokens are available, then consume them."""
        while True:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return
            wait = (tokens - self.tokens) / self.refill_rate
            log.debug(f"Rate limit: waiting {wait:.2f}s for {tokens} tokens")
            await asyncio.sleep(wait)


class RateLimiter:
    """Manages per-source rate limiting buckets."""

    DEFAULT_CAPACITY = 10
    DEFAULT_RATE = 2.0  # tokens/sec

    def __init__(self, config: dict = None):
        self._buckets: Dict[str, Bucket] = {}
        self._config = config or {}

    def _get_bucket(self, source: str) -> Bucket:
        if source not in self._buckets:
            src_cfg = self._config.get(source, {})
            capacity = src_cfg.get("capacity", self.DEFAULT_CAPACITY)
            rate = src_cfg.get("rate", self.DEFAULT_RATE)
            self._buckets[source] = Bucket(capacity=capacity, refill_rate=rate)
        return self._buckets[source]

    async def acquire(self, source: str, tokens: float = 1.0):
        """Acquire rate-limit tokens for a given source."""
        bucket = self._get_bucket(source)
        await bucket.acquire(tokens)

    def reset(self, source: str = None):
        """Reset one or all buckets."""
        if source:
            self._buckets.pop(source, None)
        else:
            self._buckets.clear()


rate_limiter = RateLimiter()
