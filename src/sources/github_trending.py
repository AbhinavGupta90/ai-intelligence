"""
GitHub Trending source — scrapes GitHub trending page for AI/ML repos.
Also checks GitHub search API for recently created repos with high stars.
"""

import re
from datetime import datetime, timezone, timedelta
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG
from src.utils.http_client import fetch_json, fetch_text
from src.utils.logger import get_logger

log = get_logger("source.github_trending")

# AI/ML topic keywords for filtering
AI_TOPICS = {
    "llm", "ai", "gpt", "machine-learning", "deep-learning", "nlp",
    "transformer", "diffusion", "agent", "rag", "langchain", "ollama",
    "chatbot", "embedding", "vector-database", "fine-tuning",
    "text-generation", "speech", "computer-vision", "multimodal",
    "artificial-intelligence", "neural-network", "pytorch", "tensorflow",
    "huggingface", "openai", "anthropic", "local-llm",
}


class GitHubTrendingSource(BaseSource):
    name = "github_trending"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("github_trending", {})
        self.languages = self.cfg.get("languages", ["python", "typescript", "rust"])
        self.min_stars = self.cfg.get("min_stars_today", 10)

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        log.info("fetching")
        items = []

        # Method 1: GitHub Search API — recently created AI repos with stars
        api_items = await self._fetch_via_search_api()
        items.extend(api_items)

        # Method 2: Scrape trending page (backup / additional signal)
        for lang in self.languages:
            scraped = await self._scrape_trending(lang)
            items.extend(scraped)

        # Deduplicate by repo URL
        seen = set()
        unique = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        log.info("fetched", total_items=len(unique))
        return unique

    async def _fetch_via_search_api(self) -> list[SourceItem]:
        """Use GitHub search API for AI repos created/pushed recently."""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        query = "topic:ai OR topic:llm OR topic:machine-learning OR topic:agent"
        url = "https://api.github.com/search/repositories"
        params = {
            "q": f"{query} pushed:>{yesterday} stars:>={self.min_stars}",
            "sort": "stars",
            "order": "desc",
            "per_page": 50,
        }
        headers = {"Accept": "application/vnd.github.v3+json"}

        data = await fetch_json(url, params=params, headers=headers)
        if not data or "items" not in data:
            return []

        items = []
        for repo in data["items"]:
            desc = (repo.get("description") or "").lower()
            name = repo.get("full_name", "").lower()
            topics = [t.lower() for t in repo.get("topics", [])]

            # AI relevance check
            all_text = f"{name} {desc} {' '.join(topics)}"
            if not any(kw in all_text for kw in AI_TOPICS):
                continue

            created = None
            if repo.get("created_at"):
                created = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))

            item = SourceItem(
                title=f"{repo.get('full_name', '')} — {repo.get('description', 'No description')[:100]}",
                url=repo.get("html_url", ""),
                source="github_trending",
                engagement=repo.get("stargazers_count", 0),
                posted_at=created,
                author=repo.get("owner", {}).get("login", ""),
                description=repo.get("description", "")[:500],
                tags=topics[:5],
                has_demo=any(kw in desc for kw in ["demo", "playground", "try it"]),
                is_open_source=True,
                external_url=repo.get("homepage", "") or "",
                item_id=f"gh-{repo.get('id', '')}",
            )
            items.append(item)

        return items

    async def _scrape_trending(self, language: str) -> list[SourceItem]:
        """Scrape GitHub trending page for a specific language."""
        url = f"https://github.com/trending/{language}?since=daily"
        html = await fetch_text(url)
        if not html:
            return []

        items = []
        # Parse repo entries from HTML (simplified regex parsing)
        repo_blocks = re.findall(
            r'<article class="Box-row">.*?</article>', html, re.DOTALL
        )

        for block in repo_blocks:
            # Extract repo path from h2 heading (not login links)
            repo_match = re.search(r'<h2[^>]*>..?<a[^>]*href="/([^"]+)"', block, re.DOTALL)
            if not repo_match:
                # Fallback: look for stargazers link pattern
                repo_match = re.search(r'href="/([^"]+)/stargazers"', block)
            if not repo_match:
                continue
            repo_path = repo_match.group(1).strip().strip("/")

            # Extract description
            desc_match = re.search(r'<p class="col-9[^"]*">(.*?)</p>', block, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""
            description = re.sub(r"<[^>]+>", "", description).strip()

            # Extract stars today
            stars_match = re.search(r'([\d,]+)\s*stars today', block)
            stars_today = int(stars_match.group(1).replace(",", "")) if stars_match else 0

            # Extract total stars from stargazers link neighbor text
            total_match = re.search(r'href="/[^"]+/stargazers"[^>]*>.*?</a>', block, re.DOTALL)
            total_stars = 0
            if total_match:
                nums = re.findall(r'([\d,]+)', total_match.group(0))
                total_stars = int(nums[0].replace(",", "")) if nums else 0

            if stars_today < self.min_stars:
                continue

            # AI relevance check
            all_text = f"{repo_path} {description}".lower()
            if not any(kw in all_text for kw in AI_TOPICS):
                continue

            item = SourceItem(
                title=f"{repo_path} — {description[:100]}",
                url=f"https://github.com/{repo_path}",
                source="github_trending",
                engagement=stars_today if stars_today > 0 else total_stars,
                author=repo_path.split("/")[0] if "/" in repo_path else "",
                description=f"⭐ {total_stars:,} total | +{stars_today:,} today — {description[:450]}",
                is_open_source=True,
                tags=[language],
                item_id=f"gh-trend-{repo_path.replace('/', '-')}",
            )
            items.append(item)

        return items
