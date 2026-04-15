"""
Daily log persistence — saves JSON + Markdown logs for each run.
Logs are organized by month: logs/2026-04/2026-04-14.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from src.config import LOGS_DIR
from src.utils.logger import get_logger

log = get_logger("persistence.daily_log")


def save_daily_log(
    items: list[dict],
    pipeline_stats: dict,
    category_counts: dict,
    velocity_alerts: int,
):
    """Save the daily run data as both JSON and Markdown."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    month_dir = LOGS_DIR / now.strftime("%Y-%m")
    month_dir.mkdir(exist_ok=True)

    # ── JSON log ──
    json_path = month_dir / f"{date_str}.json"
    json_data = {
        "date": date_str,
        "run_time": now.isoformat(),
        "pipeline_stats": pipeline_stats,
        "category_counts": category_counts,
        "velocity_alerts": velocity_alerts,
        "items": [_clean_item(item) for item in items],
    }

    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2, default=str)

    log.info("json_log_saved", path=str(json_path))

    # ── Markdown log ──
    md_path = month_dir / f"{date_str}.md"
    md_content = _format_markdown_log(items, pipeline_stats, category_counts, date_str)

    with open(md_path, "w") as f:
        f.write(md_content)

    log.info("md_log_saved", path=str(md_path))


def load_recent_urls(days: int = 7) -> set[str]:
    """Load URLs from recent logs for deduplication."""
    urls = set()
    now = datetime.now(timezone.utc)

    for day_offset in range(days):
        from datetime import timedelta
        date = now - timedelta(days=day_offset)
        month_dir = LOGS_DIR / date.strftime("%Y-%m")
        json_path = month_dir / f"{date.strftime('%Y-%m-%d')}.json"

        if not json_path.exists():
            continue

        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            for item in data.get("items", []):
                if item.get("url"):
                    urls.add(item["url"])
                if item.get("external_url"):
                    urls.add(item["external_url"])
        except (json.JSONDecodeError, KeyError):
            continue

    log.info("loaded_recent_urls", count=len(urls), days=days)
    return urls


def _clean_item(item: dict) -> dict:
    """Clean an item dict for JSON serialization."""
    # Remove internal fields
    clean = {k: v for k, v in item.items() if not k.startswith("_")}
    return clean


def _format_markdown_log(
    items: list[dict],
    pipeline_stats: dict,
    category_counts: dict,
    date_str: str,
) -> str:
    """Format a human-readable Markdown log."""
    lines = [
        f"# AI Intelligence Digest — {date_str}",
        "",
        "## Pipeline Stats",
        f"- Scanned: {pipeline_stats.get('total_scanned', 0):,}",
        f"- Pre-filtered: {pipeline_stats.get('pre_filtered', 0)}",
        f"- LLM Scored: {pipeline_stats.get('llm_scored', 0)}",
        f"- Delivered: {pipeline_stats.get('delivered', 0)}",
        f"- Sources: {pipeline_stats.get('sources_active', 0)}/{pipeline_stats.get('sources_total', 0)}",
        "",
        "## Categories",
    ]

    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {cat}: {count}")

    lines.extend(["", "## Top Items", ""])

    for i, item in enumerate(items[:20], 1):
        score = item.get("score", 0)
        title = item.get("title", "Unknown")
        url = item.get("url", "")
        cat = item.get("category", "other")
        summary = item.get("summary", "")

        lines.append(f"### {i}. [{title}]({url}) — ⭐ {score} [{cat}]")
        if summary:
            lines.append(f"> {summary}")
        lines.append("")

    return "\n".join(lines)
