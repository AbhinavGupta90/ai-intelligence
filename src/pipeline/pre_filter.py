"""
Rule-based pre-filter — eliminates 80% of noise before touching Claude API.
Zero cost, pure Python, runs on every item before LLM scoring.
"""

import re
from datetime import datetime, timezone, timedelta
from src.utils.logger import get_logger

log = get_logger("pipeline.pre_filter")

BUILD_KEYWORDS = {
    "built", "launched", "shipped", "released", "open-sourced", "open sourced",
    "demo", "prototype", "tool", "app", "framework", "library", "model",
    "fine-tuned", "fine tuned", "deployed", "introducing", "announcing",
    "we made", "i made", "i built", "i created", "just released",
    "show hn", "side project", "weekend project", "v1", "v2", "beta",
    "alpha", "mvp", "repo", "github", "playground", "api",
}

NOISE_PATTERNS = [
    r"\bhiring\b|\bjob\b|\brecruiting\b|\bwe.re looking\b",
    r"\bcourse\b|\btutorial\b|\bhow to learn\b|\bbeginner.s guide\b",
    r"\bmeme\b|\bfunny\b|\bhumor\b",
    r"\bopinion\b|\brant\b|\bhot take\b|\bunpopular opinion\b",
    r"\bstock\b|\binvest\b|\bcrypto\b|\btoken\b|\bnft\b",
]
_noise_re = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def _get(item, key, default=""):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _get_age_hours(item) -> float:
    posted_at = _get(item, "posted_at", None)
    if posted_at and isinstance(posted_at, datetime):
        delta = datetime.now(timezone.utc) - posted_at
        return max(delta.total_seconds() / 3600, 0.1)
    date_str = _get(item, "date", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - dt
            return max(delta.total_seconds() / 3600, 0.1)
        except (ValueError, AttributeError):
            pass
    age = _get(item, "age_hours", None)
    if age is not None:
        return float(age)
    return 24.0


def _get_text(item) -> str:
    title = _get(item, "title", "")
    desc = _get(item, "description", "") or _get(item, "summary", "")
    return f"{title} {desc}".lower()


def pre_filter(items: list, seen_urls: set | None = None) -> list:
    if seen_urls is None:
        seen_urls = set()
    passed = []
    stats = {"total": len(items), "too_old": 0, "duplicate": 0, "noise": 0, "low_engagement": 0, "passed": 0}
    for item in items:
        if _get_age_hours(item) > 36:
            stats["too_old"] += 1
            continue
        url = _get(item, "url", "")
        ext_url = _get(item, "external_url", "")
        if url in seen_urls or ext_url in seen_urls:
            stats["duplicate"] += 1
            continue
        text = _get_text(item)
        if _noise_re.search(text):
            stats["noise"] += 1
            continue
        source = _get(item, "source", "")
        engagement = _get(item, "engagement", 0) or 0
        if isinstance(engagement, str):
            try:
                engagement = int(engagement)
            except ValueError:
                engagement = 0
        min_eng = _min_engagement(source)
        if engagement < min_eng:
            stats["low_engagement"] += 1
            continue
        stats["passed"] += 1
        passed.append(item)
    log.info("pre_filter_complete", **stats)
    return passed


def _min_engagement(source: str) -> int:
    thresholds = {
        "reddit": 10, "hackernews": 5, "github_trending": 50,
        "producthunt": 20, "twitter": 10, "youtube": 100,
        "arxiv": 0, "devto": 5, "huggingface": 0,
    }
    return thresholds.get(source, 0)
