"""
Simple per-source rate limiter using token bucket algorithm.
Prevents hitting API limits across multiple sources.
"""

import asyncio
import time
from collections import defaultdict


class RateLimiter:
    """Token bucket rate limiter — tracks per-source request budgets."""

    def __init__(self):
        # source_name -> (tokens_remaining, last_refill_time)
        self._buckets: dict[str, dict] = defaultdict(
            lambda: {"tokens": 10, "max": 10, "refill_rate": 2.0, "last_refill": time.monotonic()}
        )

    def configure(self, source: str, max_tokens: int = 10, refill_rate: float = 2.0):
        """Set rate limit params for a specific source."""
        self._buckets[source] = {
            "tokens": max_tokens,
            "max": max_tokens,
            "refill_rate": refill_rate,  # tokens per second
            "last_refill": time.monotonic(),
        }

    async def acquire(self, source: str):
        """Wait until a token is available, then consume it."""
        bucket = self._buckets[source]

        while True:
            # Refill tokens based on elapsed time
            now = time.monotonic()
            elapsed = now - bucket["last_refill"]
            refill = elapsed * bucket["refill_rate"]
            bucket["tokens"] = min(bucket["max"], bucket["tokens"] + refill)
            bucket["last_refill"] = now

            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return
            else:
                # Wait for one token to refill
                wait_time = (1 - bucket["tokens"]) / bucket["refill_rate"]
                await asyncio.sleep(wait_time)


# Global singleton
rate_limiter = RateLimiter()
