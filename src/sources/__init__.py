from src.sources.base import SourceItem
from src.sources.reddit import RedditSource
from src.sources.hackernews import HackerNewsSource
from src.sources.github_trending import GitHubTrendingSource
from src.sources.producthunt import ProductHuntSource
from src.sources.arxiv import ArxivSource
from src.sources.devto import DevToSource
from src.sources.huggingface import HuggingFaceSource
from src.sources.twitter import TwitterSource
from src.sources.youtube import YouTubeSource

# Registry of all available sources
ALL_SOURCES = {
    "reddit": RedditSource,
    "hackernews": HackerNewsSource,
    "github_trending": GitHubTrendingSource,
    "producthunt": ProductHuntSource,
    "arxiv": ArxivSource,
    "devto": DevToSource,
    "huggingface": HuggingFaceSource,
    "twitter": TwitterSource,
    "youtube": YouTubeSource,
}

__all__ = ["SourceItem", "ALL_SOURCES"]
