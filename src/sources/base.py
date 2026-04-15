"""
Base class for all sources + the universal SourceItem data model.
Every source fetcher inherits from BaseSource and implements fetch().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import hashlib


@dataclass
class SourceItem:
    """Universal data model for a single item from any source."""

    title: str
    url: str
    source: str                         # e.g., "reddit", "hackernews"
    engagement: int = 0                 # upvotes, stars, points — raw number
    posted_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = ""
    description: str = ""               # body text / summary
    tags: list[str] = field(default_factory=list)
    has_demo: bool = False
    is_open_source: bool = False
    external_url: str = ""              # demo link, repo link if different from url
    comment_count: int = 0
    subreddit: str = ""                 # reddit-specific but useful for context
    item_id: str = ""                   # source-specific unique ID

    def __post_init__(self):
        if not self.item_id:
            # Generate a stable ID from source + url
            raw = f"{self.source}:{self.url}"
            self.item_id = hashlib.md5(raw.encode()).hexdigest()[:12]

    @property
    def age_hours(self) -> float:
        """Hours since the item was posted."""
        if not self.posted_at:
            return 24.0  # default assumption if unknown
        delta = datetime.now(timezone.utc) - self.posted_at
        return max(delta.total_seconds() / 3600, 0.1)  # min 0.1 to avoid division by zero

    @property
    def velocity(self) -> float:
        """Engagement per hour — higher = faster growing."""
        return self.engagement / self.age_hours

    def to_dict(self) -> dict:
        """Serialize for JSON logging."""
        return {
            "item_id": self.item_id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "engagement": self.engagement,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "author": self.author,
            "description": self.description[:500],
            "tags": self.tags,
            "has_demo": self.has_demo,
            "is_open_source": self.is_open_source,
            "external_url": self.external_url,
            "velocity": round(self.velocity, 2),
            "age_hours": round(self.age_hours, 1),
            "comment_count": self.comment_count,
        }


class BaseSource(ABC):
    """Abstract base class for all data sources."""

    name: str = "unknown"

    @abstractmethod
    async def fetch(self) -> list[SourceItem]:
        """Fetch items from this source. Returns list of SourceItems."""
        ...

    def is_enabled(self, config: dict) -> bool:
        """Check if this source is enabled in config."""
        return config.get(self.name, {}).get("enabled", False)
