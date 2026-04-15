"""
Shared async HTTP client — session reuse, retries, rate-limit integration.
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any

from src.logger import log
from src.rate_limiter import rate_limiter


class HttpClient:
    """Thin wrapper around aiohttp with retry logic."""

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def get(
        self,
        url: str,
        source: str = "default",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GET with rate limiting and retries. Returns parsed JSON."""
        await rate_limiter.acquire(source)
        session = await self._get_session()

        for attempt in range(1, self.max_retries + 1):
            try:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        log.warning(f"[{source}] 429 rate limited, retrying after {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        text = await resp.text()
                        log.warning(f"[{source}] HTTP {resp.status}: {text[:200]}")
                        return {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning(f"[{source}] Attempt {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    log.error(f"[{source}] All {self.max_retries} attempts failed for {url}")
                    return {}
        return {}

    async def close(self):
        """Close the underlying session."""
        if self._session and not self._session.closed:
            await self._session.close()


http_client = HttpClient()
