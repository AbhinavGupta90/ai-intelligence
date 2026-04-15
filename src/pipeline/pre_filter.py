"""
Rule-based pre-filter — eliminates 80% of noise before touching Claude API.
Zero cost, pure Python, runs on every item before LLM scoring.
"""

import re
from datetime import datetime, timezone, timedelta
from src.sources.base import SourceItem
from src.utils.logger import get_logger

log = get_logger("pipeline.pre_filter")

# ── Include signals: items containing these are likely "builds" ──
BUILD_KEYWORDS = {
    "built", "launched", "shipped", "released", "open-sourced", "open sourced",
    "demo", "prototype", "tool", "app", "framework", "library", "model",
    "fine-tuned", "fine tuned", "deployed", "introducing", "announcing",
    "we made", "i made", "i built", "i created", "just released",
    "show hn", "side project", "weekend project", "v1", "v2", "beta",
    "alpha", "mvp", "repo", "github", "playground", "api",
}

# ── Exclude signals: items matching these are noise ──
NOISE_PATTERNS = [
    r"\bhiring\b|\bjob\b|\brecruiting\b|\bwe.re looking\b",
    r"\bcourse\b|\btutorial\b|\blearn how\b|\bfree course\b",
    r"\bwhat do you think\b|\bopinion\b|\bam i the only\b",
    r"\bmeme\b|\bfunny\b|\bjoke\b",
    r"\bprompt engineering\b.*\btips\b",
]

# Compiled for performance
_noise_re = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def pre_filter(items: list[SourceItem], seen_urls: set[str] | None = None) -> list[SourceItem]:
    """
    Apply rule-based filters to raw source items.
    Returns items that pass all filters — candidates for LLM scoring.
    """
    if seen_urls is None:
        seen_urls = set()

    passed = []
    stats = {"total": len(items), "too_old": 0, "duplicate": 0, "noise": 0, "low_engagement": 0, "passed": 0}

    for item in items:
        # ── Age filter: skip posts older than 36 hours ──
        if item.age_hours > 36:
            stats["too_old"] += 1
            continue

        # ── Dedup: skip URLs seen in last 7 days ──
        if item.url in seen_urls or item.external_url in seen_urls:
            stats["duplicate"] += 1
            continue

        # ── Noise filter: skip hiring, courses, memes, opinion posts ──
        combined_text = f"{item.title} {item.description}"
        if _noise_re.search(combined_text):
            stats["noise"] += 1
            continue

        # ── Engagement floor (source-specific) ──
        # Arxiv and HuggingFace get a pass — they don't have traditional engagement
        if item.source not in ("arxiv", "huggingface"):
            if item.engagement < _min_engagement(item.source):
                stats["low_engagement"] += 1
                continue

        # ── Build signal boost (optional — items with build keywords rank higher) ──
        item_text_lower = combined_text.lower()
        has_build_signal = any(kw in item_text_lower for kw in BUILD_KEYWORDS)
        has_link = bool(item.external_url)

        # Items with build keywords OR external links are strong candidates
        # Items with neither might still pass if engagement is very high
        if not has_build_signal and not has_link and not item.is_open_source:
            if item.engagement < _min_engagement(item.source) * 3:
                # Need 3x engagement to pass without build signal
                stats["noise"] += 1
                continue

        # Track URL for dedup
        seen_urls.add(item.url)
        if item.external_url:
            seen_urls.add(item.external_url)

        passed.append(item)
        stats["passed"] += 1

    log.info("pre_filter_complete", **stats)
    return passed


def _min_engagement(source: str) -> int:
    """Source-specific minimum engagement thresholds."""
    thresholds = {
        "reddit": 50,
        "hackernews": 10,
        "producthunt": 20,
        "github_trending": 10,
        "devto": 30,
        "arxiv": 0,        # No engagement metric
        "huggingface": 3,   # Likes are lower scale
        "twitter": 50,      # Likes + RTs + replies
        "youtube": 100,     # Views + weighted likes
    }
    return thresholds.get(source, 10)
