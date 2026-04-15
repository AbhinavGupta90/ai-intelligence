"""
Hacker News source — fetches top/new stories via Algolia API.
HN is open, no auth needed, but we respect rate limits.
"""

import asyncio
from datetime import datetime, timezone
from src.sources.base import BaseSource
from src.utils.http_client import http_get
from src.utils.logger import get_logger

log = get_logger("sources.hackernews")

HN_TOP_URL = "https://hn.algolia.com/api/v1/search"
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"


class HackerNewsSource(BaseSource):
    """
    Fetches AI related stories from Hacker News via Algolia API.
    Strategy: search for AI-related keywords in last 24h, sort by points.
    """

    name = "hackernews"
    emoji = "🌰"

    async def fetch(self) -> list[dict]:
        """Fetch top AI stories from HN in last 24h."""
        queries = [
            "artificial intelligence",
            "machine learning",
            "LLM",
            "GPT",
            "Claude AI",
            "open source AI",
            "neural network",
        ]

        all_hits = []
        seen_ids = set()

        for query in queries:
            try:
                params = {
                    "query": query,
                    "tags": "story",
                    "numericFilters": f"created_at_i>{_timestamp_24h_ago()}",
                    "hitsPerPage": "20",
                }
                resp = await http_get(HN_TOP_URL, params=params)
                if resp:
                    for hit in resp.get("hits", []):
                        oid = hit.get("objectID")
                        if oid and oid not in seen_ids:
                            seen_ids.add(oid)
                            all_hits.append(hit)

                await asyncio.sleep(0.3)  # Rate limit politeness
            except Exception as e:
                log.warning("algolia_query_failed", query=query, error=str(e))

        # Sort by points and take top 20
        all_hits.sort(key=lambda h: h.get("points", 0) or 0, reverse=True)
        top_hits = all_hits[:20]

        items = []
        for hit in top_hits:
            items.append(self._parse_hit(hit))

        log.info("hn_fetch_complete", total_hits=len(all_hits), returned=len(items))
        return items

    def _parse_hit(self, hit: dict) -> dict:
        """Convert Algolia hit to our standard format."""
        oid = hit.get("objectID", "")
        points = hit.get("points", 0) or 0
        comments = hit.get("num_comments", 0) or 0

        # Engagement score: points + comments * 1.5 (comments show deeper interest)
        engagement = points + int(comments * 1.5)

        # Try to extract created date
        created = hit.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return {
            "id": f"hn_{oid}",
            "title": hit.get("title", "Untitled"),
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
            "source": "hackernews",
            "date": date_str,
            "summary": f"{points} points | {comments} comments on Hacker News",
            "engagement": engagement,
            "author": hit.get("author", ""),
            "tags": _extract_tags(hit.get("title", "")),
            "metadata": {
                "points": points,
                "comments": comments,
                "hn_url": f"https://news.ycombinator.com/item?id={oid}",
            },
        }


def _extract_tags(title: str) -> list[str]:
    """Extract AI-related tags from title."""
    tags = []
    title_lower = title.lower()

    tag_keywords = {
        "llm": ["llm", "large language model"],
        "gpt": ["gpt", "chatgpt", "openai"],
        "claude": ["claude", "anthropic"],
        "open-source": ["open source", "open-weight", "open-model"],
        "agent": ["agent", "agentic", "tool use"],
        "vision": ["vision", "image generation", "multimodal"],
        "robotics": ["robot", "robotics", "embodied"],
        "research": ["paper", "research", "arxiv", "benchmark"],
        "infra": ["inference", "deployment", "serving", "gpu", "vllm"],
    }

    for tag, keywords in tag_keywords.items():
        if any(kw in title_lower for kw in keywords):
            tags.append(tag)

    return tags or ["general-ai"]


def _timestamp_24h_ago() -> int:
    """Unix timestamp for 24h ago."""
    import time
    return int(time.time()) - 86400
