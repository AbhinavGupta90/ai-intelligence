"""
Smart deduplication & clustering.
Uses fuzzy title matching and URL comparison to merge duplicate items.
"""

from rapidfuzz import fuzz
from src.utils.logger import get_logger

log = get_logger("pipeline.dedup")


def deduplicate(items: list[dict], threshold: float = 70.0) -> list[dict]:
    """
    Remove duplicate items based on:
    1. Exact URL match
    2. Fuzzy title similarity (Levenshtein ratio > threshold)
    3. Same GitHub repo from different sources

    Keeps the highest-scored version of duplicates.
    """
    if not items:
        return items

    # Sort by score descending — first occurrence wins
    sorted_items = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
    unique = []
    seen_urls = set()
    seen_repos = set()

    for item in sorted_items:
        url = item.get("url", "")
        ext_url = item.get("external_url", "")
        title = item.get("title", "")

        # ── Check 1: Exact URL match ──
        if url in seen_urls or (ext_url and ext_url in seen_urls):
            log.debug("dedup_url", title=title[:50])
            continue

        # ── Check 2: Same GitHub repo ──
        repo = _extract_github_repo(url) or _extract_github_repo(ext_url)
        if repo and repo in seen_repos:
            log.debug("dedup_repo", title=title[:50], repo=repo)
            continue

        # ── Check 3: Fuzzy title match against already-kept items ──
        is_dup = False
        for kept in unique:
            ratio = fuzz.ratio(title.lower(), kept.get("title", "").lower())
            if ratio >= threshold:
                log.debug("dedup_fuzzy", title=title[:50], ratio=ratio)
                is_dup = True
                break

        if is_dup:
            continue

        # Item is unique — keep it
        unique.append(item)
        seen_urls.add(url)
        if ext_url:
            seen_urls.add(ext_url)
        if repo:
            seen_repos.add(repo)

    log.info("dedup_complete", before=len(items), after=len(unique), removed=len(items) - len(unique))
    return unique


def _extract_github_repo(url: str) -> str | None:
    """Extract 'owner/repo' from a GitHub URL."""
    if not url or "github.com" not in url:
        return None

    import re
    match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    if match:
        return match.group(1).lower().rstrip("/")
    return None


def cluster_by_category(items: list[dict]) -> dict[str, list[dict]]:
    """Group items by category for trend analysis."""
    clusters: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "other")
        clusters.setdefault(cat, []).append(item)
    return clusters
