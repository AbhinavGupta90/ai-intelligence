"""
Hugging Face source — fetches trending models and spaces.
Uses the HF API (no auth required for public data).
"""

from datetime import datetime, timezone
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG
from src.utils.http_client import fetch_json
from src.utils.logger import get_logger

log = get_logger("source.huggingface")


class HuggingFaceSource(BaseSource):
    name = "huggingface"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("huggingface", {})
        self.trending_only = self.cfg.get("trending_only", True)

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        log.info("fetching")
        items = []

        # Fetch trending models
        model_items = await self._fetch_models()
        items.extend(model_items)

        # Fetch trending spaces (demos/apps)
        space_items = await self._fetch_spaces()
        items.extend(space_items)

        log.info("fetched", total_items=len(items))
        return items

    async def _fetch_models(self) -> list[SourceItem]:
        """Fetch trending/recently updated models."""
        url = "https://huggingface.co/api/models"
        params = {
            "sort": "trending",
            "direction": -1,
            "limit": 30,
        }

        data = await fetch_json(url, params=params)
        if not data or not isinstance(data, list):
            return []

        items = []
        for model in data:
            model_id = model.get("modelId", "") or model.get("id", "")
            likes = model.get("likes", 0)
            downloads = model.get("downloads", 0)

            # Use likes as primary engagement metric
            if likes < 5:
                continue

            created = None
            if model.get("createdAt"):
                try:
                    created = datetime.fromisoformat(model["createdAt"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            tags = model.get("tags", [])[:5]
            pipeline_tag = model.get("pipeline_tag", "")
            if pipeline_tag:
                tags.insert(0, pipeline_tag)

            item = SourceItem(
                title=f"🤗 Model: {model_id}",
                url=f"https://huggingface.co/{model_id}",
                source="huggingface",
                engagement=likes,
                posted_at=created,
                author=model_id.split("/")[0] if "/" in model_id else "",
                description=f"Pipeline: {pipeline_tag} | Downloads: {downloads:,} | Tags: {', '.join(tags[:3])}",
                tags=tags,
                is_open_source=True,
                has_demo=False,
                item_id=f"hf-model-{model_id.replace('/', '-')}",
            )
            items.append(item)

        return items

    async def _fetch_spaces(self) -> list[SourceItem]:
        """Fetch trending Spaces (interactive demos)."""
        url = "https://huggingface.co/api/spaces"
        params = {
            "sort": "trending",
            "direction": -1,
            "limit": 30,
        }

        data = await fetch_json(url, params=params)
        if not data or not isinstance(data, list):
            return []

        items = []
        for space in data:
            space_id = space.get("id", "")
            likes = space.get("likes", 0)

            if likes < 3:
                continue

            created = None
            if space.get("createdAt"):
                try:
                    created = datetime.fromisoformat(space["createdAt"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            sdk = space.get("sdk", "unknown")
            tags = space.get("tags", [])[:5]

            item = SourceItem(
                title=f"🤗 Space: {space_id}",
                url=f"https://huggingface.co/spaces/{space_id}",
                source="huggingface",
                engagement=likes,
                posted_at=created,
                author=space_id.split("/")[0] if "/" in space_id else "",
                description=f"SDK: {sdk} | Tags: {', '.join(tags[:3])}",
                tags=tags,
                is_open_source=True,
                has_demo=True,  # Spaces ARE demos
                item_id=f"hf-space-{space_id.replace('/', '-')}",
            )
            items.append(item)

        return items
