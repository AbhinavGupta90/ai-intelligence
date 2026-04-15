"""
Source health tracker — monitors source success/failure across runs.
Tracks per-source reliability and sends alerts when a source fails 3+ days in a row.
"""

import json
from datetime import datetime, timezone, timedelta
from src.config import LOGS_DIR
from src.utils.logger import get_logger

log = get_logger("persistence.source_health")

HEALTH_PATH = LOGS_DIR / "source_health.json"


def record_source_results(source_counts: dict[str, int], source_errors: list[str]):
    """
    Record today's source results.
    source_counts: {"reddit": 45, "hackernews": 12, ...} — items fetched per source
    source_errors: ["arxiv", "devto"] — sources that failed
    """
    health = _load_health()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Initialize today's entry
    health.setdefault("daily", {})
    health["daily"][today] = {
        "success": {name: count for name, count in source_counts.items() if count > 0},
        "failed": source_errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Keep last 30 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    health["daily"] = {k: v for k, v in health["daily"].items() if k >= cutoff}

    # Update streak counters
    health["streaks"] = _calculate_failure_streaks(health["daily"])

    _save_health(health)
    log.info("source_health_recorded", success=len(source_counts), failed=len(source_errors))


def get_sources_needing_alert(threshold_days: int = 3) -> list[dict]:
    """
    Find sources that have failed for `threshold_days` consecutive days.
    Returns list of {"source": str, "consecutive_failures": int, "last_success": str}.
    """
    health = _load_health()
    streaks = health.get("streaks", {})

    alerts = []
    for source, data in streaks.items():
        consecutive = data.get("consecutive_failures", 0)
        if consecutive >= threshold_days:
            alerts.append({
                "source": source,
                "consecutive_failures": consecutive,
                "last_success": data.get("last_success", "never"),
            })

    return alerts


def get_health_summary() -> dict:
    """
    Get a summary of source health for the footer of daily digest.
    Returns: {
        "total_sources": 9,
        "healthy": 7,
        "degraded": 1,   # failed 1-2 days
        "critical": 1,   # failed 3+ days
        "details": {"reddit": "healthy", "arxiv": "critical (3 days)"}
    }
    """
    health = _load_health()
    streaks = health.get("streaks", {})

    summary = {
        "total_sources": len(streaks) if streaks else 0,
        "healthy": 0,
        "degraded": 0,
        "critical": 0,
        "details": {},
    }

    for source, data in streaks.items():
        failures = data.get("consecutive_failures", 0)
        if failures == 0:
            summary["healthy"] += 1
            summary["details"][source] = "✅"
        elif failures < 3:
            summary["degraded"] += 1
            summary["details"][source] = f"⚠️ ({failures}d)"
        else:
            summary["critical"] += 1
            summary["details"][source] = f"❌ ({failures}d)"

    return summary


def format_health_footer() -> str:
    """Format a one-line health status for the digest footer."""
    summary = get_health_summary()
    if not summary["details"]:
        return ""

    parts = []
    for source, status in sorted(summary["details"].items()):
        parts.append(f"{source} {status}")

    return f"🏥 Source Health: {' | '.join(parts)}"


def _calculate_failure_streaks(daily: dict) -> dict:
    """Calculate consecutive failure streaks for each source."""
    # Get all sources that ever appeared
    all_sources = set()
    for day_data in daily.values():
        all_sources.update(day_data.get("success", {}).keys())
        all_sources.update(day_data.get("failed", []))

    streaks = {}
    sorted_days = sorted(daily.keys(), reverse=True)  # Most recent first

    for source in all_sources:
        consecutive = 0
        last_success = "never"

        for day in sorted_days:
            day_data = daily[day]
            if source in day_data.get("failed", []):
                consecutive += 1
            elif source in day_data.get("success", {}):
                if last_success == "never":
                    last_success = day
                break  # Stop at first success going backwards
            else:
                # Source not mentioned — might not have been enabled
                break

        # Find last success date
        if last_success == "never":
            for day in sorted_days:
                if source in daily[day].get("success", {}):
                    last_success = day
                    break

        streaks[source] = {
            "consecutive_failures": consecutive,
            "last_success": last_success,
        }

    return streaks


def _load_health() -> dict:
    if not HEALTH_PATH.exists():
        return {"daily": {}, "streaks": {}}
    try:
        with open(HEALTH_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return {"daily": {}, "streaks": {}}


def _save_health(data: dict):
    with open(HEALTH_PATH, "w") as f:
        json.dump(data, f, indent=2)
