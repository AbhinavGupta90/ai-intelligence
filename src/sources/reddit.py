"""
Reddit source — fetches top posts from AI/ML subreddits via public JSON API.
No auth required for read-only access to public subreddits.
"""

import asyncio
from datetime import datetime, timezone
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG
from src.utils.http_client import fetch_json
from src.utils.logger import get_logger

log = get_logger("source.reddit")


class RedditSource(BaseSource):
    name = "reddit"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("reddit", {})
        self.subreddits = self.cfg.get("subreddits", [])
        self.min_upvotes = self.cfg.get("min_upvotes", 50)
        self.time_filter = self.cfg.get("time_filter", "day")

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        log.info("fetching", subreddits=len(self.subreddits))
        tasks = [self._fetch_subreddit(sub) for sub in self.subreddits]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items = []
        for result in results:
            if isinstance(result, Exception):
                log.warning("subreddit_error", error=str(result))
                continue
            items.extend(result)

        log.info("fetched", total_items=len(items))
        return items

    async def _fetch_subreddit(self, subreddit: str) -> list[SourceItem]:
        """Fetch top posts from a single subreddit."""
        url = f"https://www.reddit.com/r/{subreddit}/top.json"
        params = {"t": self.time_filter, "limit": 100}
        headers = {"User-Agent": "AI-Intelligence-Bot/1.0"}

        data = await fetch_json(url, params=params, headers=headers)
        if not data or "data" not in data:
            log.warning("empty_response", subreddit=subreddit)
            return []

        items = []
        for post in data["data"].get("children", []):
            d = post.get("data", {})
            score = d.get("score", 0)

            # Pre-filter: skip low-engagement posts
            if score < self.min_upvotes:
                continue

            created = datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc)

            item = SourceItem(
                title=d.get("title", ""),
                url=f"https://reddit.com{d.get('permalink', '')}",
                source="reddit",
                engagement=score,
                posted_at=created,
                author=d.get("author", ""),
                description=d.get("selftext", "")[:1000],
                has_demo="demo" in d.get("title", "").lower() or "demo" in d.get("selftext", "").lower(),
                is_open_source="github.com" in d.get("url", ""),
                external_url=d.get("url", "") if d.get("is_self") is False else "",
                comment_count=d.get("num_comments", 0),
                subreddit=subreddit,
                tags=[subreddit],
            )
            items.append(item)

        return items
