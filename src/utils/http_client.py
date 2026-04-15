"""
Async HTTP client with retries, timeouts, and rate-limit awareness.
All source fetchers use this instead of raw httpx.
"""

import httpx
import asyncio
from typing import Optional
from src.utils.logger import get_logger

log = get_logger("http_client")

# Shared client instance (created lazily)
_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    """Get or create the shared async HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            headers={"User-Agent": "AI-Intelligence-Digest/1.0"},
        )
    return _client


async def fetch_json(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    retries: int = 2,
    retry_delay: float = 5.0,
) -> Optional[dict | list]:
    """
    Fetch JSON from a URL with automatic retries.
    Returns None on total failure (caller handles gracefully).
    """
    client = await get_client()

    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, params=params, headers=headers)

            # Rate limited â back off
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", retry_delay * 2))
                log.warning("rate_limited", url=url, wait_seconds=wait)
                await asyncio.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except httpx.HTTPStatusError as e:
            log.warning("http_error", url=url, status=e.response.status_code, attempt=attempt + 1)
        except httpx.RequestError as e:
            log.warning("request_error", url=url, error=str(e), attempt=attempt + 1)
        except Exception as e:
            log.warning("unexpected_error", url=url, error=str(e), attempt=attempt + 1)

        if attempt < retries:
            await asyncio.sleep(retry_delay * (attempt + 1))

    log.error("fetch_failed", url=url, retries=retries)
    return None


async def fetch_text(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> Optional[str]:
    """Fetch raw text content from a URL."""
    client = await get_client()
    try:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log.warning("text_fetch_failed", url=url, error=str(e))
        return None


async def close_client():
    """Close the shared HTTP client. Call at shutdown."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None

# Alias for backward compatibility
http_get = fetch_json
