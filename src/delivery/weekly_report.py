"""
Weekly intelligence report — generated every Sunday.
Aggregates the week's data into trends, top builds, and predictions.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from src.config import LOGS_DIR
from src.persistence.knowledge_graph import get_trending_categories, get_prolific_builders
from src.intelligence.trend_tracker import get_category_sparklines
from src.intelligence.builder_tracker import get_rising_builders
from src.intelligence.project_tracker import get_breakout_projects
from src.intelligence.predictor import generate_predictions
from src.delivery.telegram import send_telegram_message
from src.feedback.handler import get_taste_accuracy
from src.utils.logger import get_logger

log = get_logger("delivery.weekly_report")


async def generate_and_send_weekly_report():
    """Compile and send the weekly intelligence report."""
    log.info("generating_weekly_report")

    # Gather data from the past 7 days
    week_items = _load_week_items()
    if not week_items:
        log.warning("no_data_for_weekly_report")
        return

    # Top 5 builds of the week
    top_5 = sorted(week_items, key=lambda x: x.get("score", 0), reverse=True)[:5]

    # Category trends
    trends = get_trending_categories(weeks=4)

    # Prolific builders
    prolific = get_prolific_builders(min_appearances=2)

    # Weekly stats
    total_scanned = sum(d.get("pipeline_stats", {}).get("total_scanned", 0) for d in _load_week_logs())
    total_delivered = len(week_items)

    # Taste accuracy
    taste = get_taste_accuracy()

    # Generate insight using Claude (if available)
    insight = await _generate_weekly_insight(top_5, trends)

    # Format the report
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=7)).strftime("%B %d")
    week_end = now.strftime("%B %d, %Y")

    lines = [
        f"📊 <b>AI Weekly Intelligence — {week_start} - {week_end}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🏆 <b>TOP 5 BUILDS OF THE WEEK:</b>",
    ]

    for i, item in enumerate(top_5, 1):
        title = _esc(item.get("title", "Unknown")[:70])
        score = item.get("score", 0)
        why = _esc(item.get("why_interesting", "")[:100])
        lines.append(f"{i}. <b>{title}</b> ⭐{score}")
        if why:
            lines.append(f"   — {why}")

    lines.extend(["", "📈 <b>RISING CATEGORIES (vs last week):</b>"])
    for r in trends.get("rising", []):
        lines.append(f"- {r['category']}: {r['from']} → {r['to']} (+{r['change_pct']}%) 🔥")

    if trends.get("declining"):
        lines.extend(["", "📉 <b>DECLINING:</b>"])
        for d in trends["declining"]:
            lines.append(f"- {d['category']}: {d['from']} → {d['to']} ({d['change_pct']}%)")

    if trends.get("new"):
        lines.extend(["", "🆕 <b>NEW CATEGORY EMERGED:</b>"])
        for n in trends["new"]:
            lines.append(f"- \"{n['category']}\" — {n['count']} posts this week")

    if prolific:
        lines.extend(["", "👤 <b>PROLIFIC BUILDERS:</b>"])
        for b in prolific[:5]:
            projects = ", ".join(b["projects"][:2])
            lines.append(f"- {_esc(b['name'])}: {b['appearances']} appearances — {_esc(projects)}")

    # Breakout projects (cross-source traction)
    breakouts = get_breakout_projects()
    if breakouts:
        lines.extend(["", "💙 <b>BREAKOUT PROJECTS:</b>"])
        for bp in breakouts[:3]:
            lines.append(f"- {_esc(bp['title'][:60])} — {bp['reason']} ({', '.join(bp['sources'])})")

    # Rising builders (new faces shipping quality)
    rising = get_rising_builders()
    if rising:
        lines.extend(["", "🌟 <b>RISING BUILDERS (new this fortnight):</b>"])
        for rb in rising[:3]:
            projects = ", ".join(rb["projects"][:2])
            lines.append(f"- {_esc(rb['name'])} — avg ⭐{rb['avg_score']} — {_esc(projects)}")

    if insight:
        lines.extend(["", "💡 <b>WEEKLY INSIGHT:</b>", f"<i>{_esc(insight)}</i>"])

    # Predictions
    predictions = await generate_predictions()
    if predictions:
        lines.extend(["", "🔮 <b>PREDICTIONS:</b>"])
        for pred in predictions[:3]:
            conf = pred.get("confidence", "medium")
            conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "⚪")
            lines.append(f"{conf_emoji} {_esc(pred.get('prediction', '')[:150])}")
            if pred.get("timeframe"):
                lines.append(f"   ⏱️ {pred['timeframe']}")

    # Category sparklines
    sparklines = get_category_sparklines(weeks=8)
    if sparklines:
        lines.extend(["", "📈 <b>CATEGORY TRENDS (8 weeks):</b>"])
        for cat, spark in sorted(sparklines.items(), key=lambda x: -len(x[1].replace("▁", ""))):
            lines.append(f"  {cat}: {spark}")
            if len(lines) > 80:  # Keep message size reasonable
                break

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 STATS: {total_scanned:,} posts scanned | {total_delivered} delivered",
    ])

    if taste is not None:
        lines.append(f"🎯 Taste Accuracy: {taste:.0%}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    text = "\n".join(lines)
    await send_telegram_message(text)
    log.info("weekly_report_sent")


async def _generate_weekly_insight(top_items: list[dict], trends: dict) -> str:
    """Use LLM (Gemini free / Anthropic) to generate a 2-3 sentence weekly insight."""
    from src.utils.llm import generate

    context = json.dumps({
        "top_builds": [{"title": i.get("title", ""), "category": i.get("category", "")} for i in top_items],
        "rising": trends.get("rising", []),
        "declining": trends.get("declining", []),
    }, indent=2)

    result = await generate(
        prompt=f"Based on this week's AI build data, write a 2-3 sentence insight about the most interesting trend. Be specific and opinionated:\n{context}",
        max_tokens=200,
    )
    return result or ""


def _load_week_items() -> list[dict]:
    """Load all scored items from the past 7 days."""
    items = []
    for log_data in _load_week_logs():
        items.extend(log_data.get("items", []))
    return items


def _load_week_logs() -> list[dict]:
    """Load daily log JSON files from the past 7 days."""
    logs = []
    now = datetime.now(timezone.utc)

    for day_offset in range(7):
        date = now - timedelta(days=day_offset)
        month_dir = LOGS_DIR / date.strftime("%Y-%m")
        json_path = month_dir / f"{date.strftime('%Y-%m-%d')}.json"

        if json_path.exists():
            try:
                with open(json_path, "r") as f:
                    logs.append(json.load(f))
            except json.JSONDecodeError:
                continue

    return logs


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
