"""
YouTube source — fetches AI demo/build videos with high view velocity.
Requires YouTube Data API v3 key (set YOUTUBE_API_KEY in env).
Focuses on videos uploaded in last 24h with rapid view growth.
"""

from datetime import datetime, timezone, timedelta
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG, YOUTUBE_API_KEY
from src.utils.http_client import fetch_json
from src.utils.logger import get_logger

log = get_logger("source.youtube")

# Search queries to find AI builder content
SEARCH_QUERIES = [
    "AI demo 2026",
    "built with AI",
    "open source AI tool",
    "LLM agent demo",
    "AI project showcase",
]

AI_KEYWORDS = {
    "ai", "llm", "gpt", "agent", "demo", "built", "open source",
    "machine learning", "deep learning", "model", "fine-tune",
    "langchain", "ollama", "huggingface", "multimodal", "voice ai",
    "local model", "on-device", "real-time",
}


class YouTubeSource(BaseSource):
    name = "youtube"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("youtube", {})
        self.min_views_per_hour = self.cfg.get("min_views_per_hour", 100)

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        if not YOUTUBE_API_KEY:
            log.warning("no_api_key", msg="YOUTUBE_API_KEY not set — skipping YouTube")
            return []

        log.info("fetching")
        items = []
        seen_ids = set()

        for query in SEARCH_QUERIES:
            results = await self._search(query)
            for item in results:
                if item.item_id not in seen_ids:
                    seen_ids.add(item.item_id)
                    items.append(item)

        log.info("fetched", total_items=len(items))
        return items

    async def _search(self, query: str) -> list[SourceItem]:
        """Search YouTube for recent AI videos."""
        since = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Step 1: Search for videos
        search_url = "https://www.googleapis.com/youtube/v3/search"
        search_params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": since,
            "maxResults": 20,
            "key": YOUTUBE_API_KEY,
        }

        search_data = await fetch_json(search_url, params=search_params)
        if not search_data or "items" not in search_data:
            return []

        # Collect video IDs for stats lookup
        video_ids = []
        snippets = {}
        for item in search_data["items"]:
            vid_id = item.get("id", {}).get("videoId", "")
            if vid_id:
                video_ids.append(vid_id)
                snippets[vid_id] = item.get("snippet", {})

        if not video_ids:
            return []

        # Step 2: Get video statistics (views, likes)
        stats_url = "https://www.googleapis.com/youtube/v3/videos"
        stats_params = {
            "part": "statistics,contentDetails",
            "id": ",".join(video_ids),
            "key": YOUTUBE_API_KEY,
        }

        stats_data = await fetch_json(stats_url, params=stats_params)
        if not stats_data or "items" not in stats_data:
            return []

        items = []
        for video in stats_data["items"]:
            vid_id = video.get("id", "")
            stats = video.get("statistics", {})
            snippet = snippets.get(vid_id, {})

            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))

            # Parse publish time
            published = None
            pub_str = snippet.get("publishedAt", "")
            if pub_str:
                try:
                    published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            # Calculate view velocity
            age_hours = 1.0
            if published:
                delta = datetime.now(timezone.utc) - published
                age_hours = max(delta.total_seconds() / 3600, 0.5)

            views_per_hour = views / age_hours

            if views_per_hour < self.min_views_per_hour:
                continue

            title = snippet.get("title", "")
            description = snippet.get("description", "")
            channel = snippet.get("channelTitle", "")

            # AI relevance check
            combined = f"{title} {description}".lower()
            if not any(kw in combined for kw in AI_KEYWORDS):
                continue

            # Detect build/demo signals
            has_demo = any(kw in combined for kw in ["demo", "tutorial", "walkthrough", "showcase", "how i built"])
            is_oss = "github" in combined

            # Extract tags from description
            tags = []
            for kw in AI_KEYWORDS:
                if kw in combined:
                    tags.append(kw)
                if len(tags) >= 5:
                    break

            item = SourceItem(
                title=title[:140],
                url=f"https://www.youtube.com/watch?v={vid_id}",
                source="youtube",
                engagement=views + likes * 10,  # Weighted: likes count more
                posted_at=published,
                author=channel,
                description=description[:500],
                tags=tags,
                has_demo=has_demo,
                is_open_source=is_oss,
                external_url="",
                comment_count=comments,
                item_id=f"yt-{vid_id}",
            )
            items.append(item)

        return items
