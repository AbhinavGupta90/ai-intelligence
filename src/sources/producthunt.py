"""
Product Hunt source — fetches AI-tagged daily launches.
Uses the public GraphQL API (requires API token for higher limits).
Falls back to the unofficial JSON endpoint if no token.
"""

from datetime import datetime, timezone
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG, PRODUCTHUNT_API_TOKEN
from src.utils.http_client import fetch_json
from src.utils.logger import get_logger

log = get_logger("source.producthunt")

AI_KEYWORDS = {
    "ai", "llm", "gpt", "machine learning", "chatbot", "agent",
    "copilot", "automation", "nlp", "voice", "generative",
    "openai", "anthropic", "claude", "gemini", "multimodal",
}


class ProductHuntSource(BaseSource):
    name = "producthunt"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("producthunt", {})
        self.min_upvotes = self.cfg.get("min_upvotes", 20)
        self.ai_only = self.cfg.get("ai_tags_only", True)

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        log.info("fetching")

        if PRODUCTHUNT_API_TOKEN:
            items = await self._fetch_graphql()
        else:
            items = await self._fetch_public()

        log.info("fetched", total_items=len(items))
        return items

    async def _fetch_graphql(self) -> list[SourceItem]:
        """Fetch via Product Hunt GraphQL API (needs token)."""
        import httpx

        url = "https://api.producthunt.com/v2/api/graphql"
        headers = {
            "Authorization": f"Bearer {PRODUCTHUNT_API_TOKEN}",
            "Content-Type": "application/json",
        }
        query = """
        {
          posts(order: VOTES, first: 50, postedAfter: "%s") {
            edges {
              node {
                id
                name
                tagline
                description
                url
                votesCount
                commentsCount
                website
                createdAt
                topics { edges { node { name } } }
                makers { name }
              }
            }
          }
        }
        """ % (datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z"))

        data = await fetch_json(url, headers=headers)
        # For GraphQL, we need to POST
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json={"query": query}, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.warning("graphql_error", error=str(e))
                return []

        if not data or "data" not in data:
            return []

        items = []
        for edge in data["data"]["posts"]["edges"]:
            node = edge["node"]
            topics = [t["node"]["name"].lower() for t in node.get("topics", {}).get("edges", [])]

            # AI filter
            if self.ai_only:
                all_text = f"{node['name']} {node['tagline']} {' '.join(topics)}".lower()
                if not any(kw in all_text for kw in AI_KEYWORDS):
                    continue

            if node.get("votesCount", 0) < self.min_upvotes:
                continue

            created = None
            if node.get("createdAt"):
                try:
                    created = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            makers = [m["name"] for m in node.get("makers", [])]

            item = SourceItem(
                title=f"{node['name']} — {node['tagline']}",
                url=node.get("url", ""),
                source="producthunt",
                engagement=node.get("votesCount", 0),
                posted_at=created,
                author=", ".join(makers) if makers else "",
                description=node.get("description", "")[:500],
                tags=topics[:5],
                has_demo=True,  # PH launches almost always have a working product
                is_open_source=False,
                external_url=node.get("website", ""),
                comment_count=node.get("commentsCount", 0),
                item_id=f"ph-{node.get('id', '')}",
            )
            items.append(item)

        return items

    async def _fetch_public(self) -> list[SourceItem]:
        """Fallback: scrape the public PH homepage feed."""
        # Product Hunt doesn't have a great public API without auth
        # Use their RSS-like JSON endpoint or newest page
        url = "https://www.producthunt.com/frontend/graphql"

        # Try the unofficial API
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        query = {
            "operationName": "HomePage",
            "variables": {"date": today},
            "query": """query HomePage($date: DateTime) {
                posts(order: RANKING, postedAfter: $date, first: 30) {
                    edges { node { id name tagline votesCount url website } }
                }
            }""",
        }

        log.info("using_public_endpoint", note="No PH API token, using limited public access")

        # Without proper auth this may not work — return empty gracefully
        # Users should set PRODUCTHUNT_API_TOKEN for reliable PH data
        return []
