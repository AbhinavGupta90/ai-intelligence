"""
Project tracking intelligence -- identifies trending and breakout projects.
Maintains projects.json with mention counts, score trends, and source tracking.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from src.config import KNOWLEDGE_DIR
from src.utils.logger import get_logger

log = get_logger("intelligence.project_tracker")

PROJECTS_PATH = KNOWLEDGE_DIR / "projects.json"


def get_trending_projects(min_mentions=2) -> list[dict]:
    """
    Find projects mentioned across multiple sources or days.
    Returns list of dicts with keys:
    - name: project name
    - mention_count: total mentions
    - sources: set of source names mentioning it
    - avg_score: average score across mentions
    - momentum: trend in score over time
    """
    projects = _load_json(PROJECTS_PATH, {})
    trending = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)

    for name, data in projects.items():
        mentions = data.get("mentions", 0)
        if mentions < min_mentions:
            continue

        sources = data.get("sources", [])
        scores = data.get("scores", [])
        timestamps = data.get("timestamps", [])

        # Filter to recent mentions
        recent_scores = [
            scores[i] for i in range(len(timestamps))
            if datetime.fromisoformat(timestamps[i]) > cutoff
        ]

        if recent_scores:
            avg_score = sum(recent_scores) / len(recent_scores)
            momentum = recent_scores[-1] - recent_scores[0] if len(recent_scores) > 1 else 0
            trending.append({
                "name": name,
                "mention_count": mentions,
                "sources": list(set(sources)),
                "avg_score": avg_score,
                "momentum": momentum,
                "recent_mentions": len(recent_scores)
            })

    # Sort by mention count descending
    trending.sort(key=lambda x: x["mention_count"], reverse=True)
    return trending


def get_breakout_projects(days=7) -> list[dict]:
    """
    Find projects that recently gained significant momentum
    (score trend going up).
    Returns list of dicts with keys:
    - name: project name
    - momentum: score delta from start to end of window
    - recent_score: most recent score
    - velocity: rate of score increase
    """
    projects = _load_json(PROJECTS_PATH, {})
    breakouts = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    for name, data in projects.items():
        scores = data.get("scores", [])
        timestamps = data.get("timestamps", [])

        # Filter to recent window
        recent_indices = [
            i for i in range(len(timestamps))
            if datetime.fromisoformat(timestamps[i]) > cutoff
        ]

        if len(recent_indices) < 2:
            continue

        recent_scores = [scores[i] for i in recent_indices]
        momentum = recent_scores[-1] - recent_scores[0]

        # Only include projects with positive momentum
        if momentum > 0:
            velocity = momentum / len(recent_scores)
            breakouts.append({
                "name": name,
                "momentum": momentum,
                "recent_score": recent_scores[-1],
                "velocity": velocity,
                "mentions_in_window": len(recent_indices)
            })

    # Sort by momentum descending
    breakouts.sort(key=lambda x: x["momentum"], reverse=True)
    return breakouts


def get_project_stats() -> dict:
    """
    Get aggregate statistics about tracked projects.
    Returns dict with total count, average mentions, top projects, etc.
    Used by predictor for context gathering.
    """
    projects = _load_json(PROJECTS_PATH, {})
    if not projects:
        return {"total_projects": 0, "avg_mentions": 0, "top_projects": [], "multi_source_count": 0}

    mention_counts = [d.get("mentions", 0) for d in projects.values()]
    total = len(projects)
    avg_mentions = sum(mention_counts) / total if total else 0

    # Top 5 by mentions
    sorted_projects = sorted(projects.items(), key=lambda x: x[1].get("mentions", 0), reverse=True)
    top_projects = [
        {"name": name, "mentions": data.get("mentions", 0), "sources": len(data.get("sources", []))}
        for name, data in sorted_projects[:5]
    ]

    return {
        "total_projects": total,
        "avg_mentions": round(avg_mentions, 1),
        "top_projects": top_projects,
        "multi_source_count": sum(1 for d in projects.values() if len(d.get("sources", [])) > 1),
    }


def update_project_tracking(scored_items: list[dict]):
    """
    Update projects.json with new items.
    For each item with a "project" field:
    - Increment mention count
    - Add source name to sources list
    - Append score and timestamp to history
    """
    projects = _load_json(PROJECTS_PATH, {})
    now = datetime.now(timezone.utc).isoformat()

    for item in scored_items:
        project_name = item.get("project")
        if not project_name:
            continue

        if project_name not in projects:
            projects[project_name] = {
                "mentions": 0,
                "sources": [],
                "scores": [],
                "timestamps": [],
                "created_at": now
            }

        data = projects[project_name]
        data["mentions"] = data.get("mentions", 0) + 1
        data["mentions_updated_at"] = now

        # Track source if present
        source = item.get("source", "unknown")
        if source not in data.get("sources", []):
            data.setdefault("sources", []).append(source)

        # Append score and timestamp
        score = item.get("final_score", 0)
        data.setdefault("scores", []).append(score)
        data.setdefault("timestamps", []).append(now)

        # Keep only last 100 scores to avoid unbounded growth
        if len(data["scores"]) > 100:
            data["scores"] = data["scores"][-100:]
            data["timestamps"] = data["timestamps"][-100:]

    _save_json(PROJECTS_PATH, projects)
    log.info(f"Updated tracking for {len([i for i in scored_items if i.get('project')])} project mentions")


def _load_json(path: Path, default) -> dict:
    """Load JSON file with default fallback."""
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load {path}: {e}")
        return default


def _save_json(path: Path, data: dict):
    """Save JSON to file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save {path}: {e}")
