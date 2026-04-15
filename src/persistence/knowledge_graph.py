"""
Knowledge graph persistence — tracks builders, projects, and category trends.
Updated after each daily run with new data points.
"""

import json
from datetime import datetime, timezone
from src.config import KNOWLEDGE_DIR
from src.utils.logger import get_logger

log = get_logger("persistence.knowledge_graph")

BUILDERS_PATH = KNOWLEDGE_DIR / "builders.json"
PROJECTS_PATH = KNOWLEDGE_DIR / "projects.json"
CATEGORIES_PATH = KNOWLEDGE_DIR / "categories.json"


def update_knowledge_graph(items: list[dict], category_counts: dict):
    """Update all knowledge graph files with today's data."""
    _update_builders(items)
    _update_projects(items)
    _update_categories(category_counts)


def _update_builders(items: list[dict]):
    """Track recurring builders and their output."""
    builders = _load_json(BUILDERS_PATH, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for item in items:
        author = item.get("author", "").strip()
        if not author or author == "unknown":
            continue

        if author not in builders:
            builders[author] = {
                "first_seen": today,
                "appearances": 0,
                "scores": [],
                "categories": [],
                "projects": [],
            }

        b = builders[author]
        b["appearances"] += 1
        b["scores"].append(item.get("score", 0))
        b["avg_score"] = round(sum(b["scores"]) / len(b["scores"]), 1)

        cat = item.get("category", "other")
        if cat not in b["categories"]:
            b["categories"].append(cat)

        title = item.get("title", "")[:80]
        if title and title not in b["projects"]:
            b["projects"].append(title)
            # Keep last 10 projects only
            b["projects"] = b["projects"][-10:]

        # Keep last 20 scores only
        b["scores"] = b["scores"][-20:]

    _save_json(BUILDERS_PATH, builders)
    log.info("builders_updated", total_builders=len(builders))


def _update_projects(items: list[dict]):
    """Track project mentions and score trends."""
    projects = _load_json(PROJECTS_PATH, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for item in items:
        # Use URL as project key (most stable identifier)
        url = item.get("external_url") or item.get("url", "")
        if not url:
            continue

        title = item.get("title", "Unknown")[:80]

        if url not in projects:
            projects[url] = {
                "title": title,
                "first_seen": today,
                "mentions": 0,
                "score_trend": [],
                "sources": [],
                "category": item.get("category", "other"),
            }

        p = projects[url]
        p["mentions"] += 1
        p["score_trend"].append(item.get("score", 0))
        p["score_trend"] = p["score_trend"][-10:]  # Keep last 10

        source = item.get("source", "")
        if source and source not in p["sources"]:
            p["sources"].append(source)

    _save_json(PROJECTS_PATH, projects)
    log.info("projects_updated", total_projects=len(projects))


def _update_categories(category_counts: dict):
    """Store weekly category snapshots for trend analysis."""
    categories = _load_json(CATEGORIES_PATH, {})
    now = datetime.now(timezone.utc)
    week_key = f"{now.year}-W{now.isocalendar()[1]:02d}"

    if week_key not in categories:
        categories[week_key] = {}

    # Accumulate counts for the week
    for cat, count in category_counts.items():
        categories[week_key][cat] = categories[week_key].get(cat, 0) + count

    # Keep last 26 weeks (6 months)
    if len(categories) > 26:
        oldest_keys = sorted(categories.keys())[: len(categories) - 26]
        for key in oldest_keys:
            del categories[key]

    _save_json(CATEGORIES_PATH, categories)
    log.info("categories_updated", week=week_key)


def get_trending_categories(weeks: int = 4) -> dict:
    """
    Compare recent weeks to find rising/declining categories.
    Returns dict with 'rising', 'declining', 'new' lists.
    """
    categories = _load_json(CATEGORIES_PATH, {})
    sorted_weeks = sorted(categories.keys())

    if len(sorted_weeks) < 2:
        return {"rising": [], "declining": [], "new": []}

    recent = sorted_weeks[-1]
    previous = sorted_weeks[-2]

    recent_data = categories[recent]
    prev_data = categories[previous]

    rising = []
    declining = []
    new_cats = []

    all_cats = set(list(recent_data.keys()) + list(prev_data.keys()))
    for cat in all_cats:
        curr = recent_data.get(cat, 0)
        prev = prev_data.get(cat, 0)

        if prev == 0 and curr > 0:
            new_cats.append({"category": cat, "count": curr})
        elif curr > prev * 1.2:  # 20%+ increase
            pct = ((curr - prev) / max(prev, 1)) * 100
            rising.append({"category": cat, "from": prev, "to": curr, "change_pct": round(pct)})
        elif curr < prev * 0.8:  # 20%+ decrease
            pct = ((prev - curr) / max(prev, 1)) * 100
            declining.append({"category": cat, "from": prev, "to": curr, "change_pct": round(-pct)})

    rising.sort(key=lambda x: x["change_pct"], reverse=True)
    declining.sort(key=lambda x: x["change_pct"])

    return {"rising": rising[:5], "declining": declining[:5], "new": new_cats}


def get_prolific_builders(min_appearances: int = 2) -> list[dict]:
    """Find builders who shipped multiple things recently."""
    builders = _load_json(BUILDERS_PATH, {})
    prolific = []

    for name, data in builders.items():
        if data.get("appearances", 0) >= min_appearances:
            prolific.append({
                "name": name,
                "appearances": data["appearances"],
                "avg_score": data.get("avg_score", 0),
                "projects": data.get("projects", [])[-3:],
            })

    prolific.sort(key=lambda x: x["appearances"], reverse=True)
    return prolific[:10]


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return default


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
