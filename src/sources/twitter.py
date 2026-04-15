"""
Twitter/X source — fetches AI-related tweets via Twitter API v2.
Requires Bearer Token (set TWITTER_BEARER_TOKEN in env).
Tracks hashtags like #BuildWithAI, #AItools and AI influencer accounts.
"""

from datetime import datetime, timezone, timedelta
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG, TWITTER_BEARER_TOKEN
from src.utils.http_client import fetch_json
from src.utils.logger import get_logger

log = get_logger("source.twitter")

# AI builder influencers to track (add/remove as needed)
AI_ACCOUNTS = [
    "kaboroevich", "swaboroevich",  # placeholder handles — replace with real ones
]

AI_KEYWORDS_QUERY = (
    "(#BuildWithAI OR #AItools OR #opensource AI OR shipped AI OR launched AI "
    "OR built with LLM OR open source model OR AI agent OR local LLM) "
    "-is:retweet lang:en"
)


class TwitterSource(BaseSource):
    name = "twitter"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("twitter", {})
        self.min_likes = self.cfg.get("min_likes", 50)
        self.hashtags = self.cfg.get("hashtags", ["BuildWithAI", "AItools"])

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        if not TWITTER_BEARER_TOKEN:
            log.warning("no_bearer_token", msg="TWITTER_BEARER_TOKEN not set — skipping Twitter")
            return []

        log.info("fetching")
        items = []

        # Search recent tweets matching AI build keywords
        search_items = await self._search_recent()
        items.extend(search_items)

        log.info("fetched", total_items=len(items))
        return items

    async def _search_recent(self) -> list[SourceItem]:
        """Search Twitter API v2 for recent AI builder tweets."""
        url = "https://api.twitter.com/2/tweets/search/recent"

        # Build query from configured hashtags + base keywords
        hashtag_part = " OR ".join(f"#{h}" for h in self.hashtags)
        query = (
            f"({hashtag_part} OR built AI OR shipped AI OR launched AI OR open source model) "
            f"-is:retweet lang:en"
        )

        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "query": query[:512],  # Twitter query max 512 chars
            "max_results": 100,
            "sort_order": "relevancy",
            "start_time": since,
            "tweet.fields": "created_at,public_metrics,author_id,entities",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}

        data = await fetch_json(url, params=params, headers=headers)
        if not data or "data" not in data:
            log.warning("empty_response")
            return []

        # Build author lookup
        authors = {}
        for user in data.get("includes", {}).get("users", []):
            authors[user["id"]] = user.get("username", "")

        items = []
        for tweet in data["data"]:
            metrics = tweet.get("public_metrics", {})
            likes = metrics.get("like_count", 0)

            if likes < self.min_likes:
                continue

            created = None
            if tweet.get("created_at"):
                try:
                    created = datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            tweet_id = tweet.get("id", "")
            author_id = tweet.get("author_id", "")
            username = authors.get(author_id, "unknown")
            text = tweet.get("text", "")

            # Extract URLs from entities
            urls = []
            for url_entity in tweet.get("entities", {}).get("urls", []):
                expanded = url_entity.get("expanded_url", "")
                # Skip twitter internal links
                if expanded and "twitter.com" not in expanded and "t.co" not in expanded:
                    urls.append(expanded)

            # Detect build signals
            text_lower = text.lower()
            has_demo = any(kw in text_lower for kw in ["demo", "try it", "playground", "check it out", "live at"])
            is_oss = "github.com" in " ".join(urls)

            # Extract hashtags
            tags = [
                ht.get("tag", "")
                for ht in tweet.get("entities", {}).get("hashtags", [])
            ][:5]

            engagement = likes + metrics.get("retweet_count", 0) + metrics.get("reply_count", 0)

            item = SourceItem(
                title=text[:140],  # First 140 chars as title
                url=f"https://twitter.com/{username}/status/{tweet_id}",
                source="twitter",
                engagement=engagement,
                posted_at=created,
                author=f"@{username}",
                description=text[:500],
                tags=tags,
                has_demo=has_demo,
                is_open_source=is_oss,
                external_url=urls[0] if urls else "",
                comment_count=metrics.get("reply_count", 0),
                item_id=f"tw-{tweet_id}",
            )
            items.append(item)

        return items
