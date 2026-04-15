"""
Dev.to source — fetches AI-tagged articles with high engagement.
Uses the public Forem API (no auth required).
"""

from datetime import datetime, timezone
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG
from src.utils.http_client import fetch_json
from src.utils.logger import get_logger

log = get_logger("source.devto")

AI_TAGS = ["ai", "machinelearning", "llm", "gpt", "openai", "chatgpt", "generativeai",
           "deeplearning", "nlp", "huggingface", "langchain", "agents"]


class DevToSource(BaseSource):
    name = "devto"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("devto", {})
        self.min_reactions = self.cfg.get("min_reactions", 30)

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        log.info("fetching")
        items = []

        for tag in AI_TAGS[:6]:  # Limit to avoid too many API calls
            tag_items = await self._fetch_tag(tag)
            items.extend(tag_items)

        # Dedup by URL
        seen = set()
        unique = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        log.info("fetched", total_items=len(unique))
        return unique

    async def _fetch_tag(self, tag: str) -> list[SourceItem]:
        """Fetch recent articles for a specific tag."""
        url = "https://dev.to/api/articles"
        params = {
            "tag": tag,
            "top": 1,  # top from last 1 day
            "per_page": 30,
        }

        data = await fetch_json(url, params=params)
        if not data or not isinstance(data, list):
            return []

        items = []
        for article in data:
            reactions = article.get("public_reactions_count", 0)
            if reactions < self.min_reactions:
                continue

            published = None
            if article.get("published_at"):
                try:
                    published = datetime.fromisoformat(
                        article["published_at"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            tags = article.get("tag_list", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]

            item = SourceItem(
                title=article.get("title", ""),
                url=article.get("url", ""),
                source="devto",
                engagement=reactions,
                posted_at=published,
                author=article.get("user", {}).get("username", ""),
                description=article.get("description", "")[:500],
                tags=tags[:5],
                has_demo="github.com" in article.get("url", "") or "demo" in article.get("title", "").lower(),
                is_open_source="github" in (article.get("description", "") or "").lower(),
                comment_count=article.get("comments_count", 0),
                item_id=f"devto-{article.get('id', '')}",
            )
            items.append(item)

        return items
