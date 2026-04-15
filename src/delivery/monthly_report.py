"""
Monthly deep dive report — generated on the 1st of each month.
Top 20 builds, category evolution, prediction scorecard, taste evolution.
"""

import json
from datetime import datetime, timezone, timedelta
from src.config import LOGS_DIR, KNOWLEDGE_DIR, FEEDBACK_PATH
from src.intelligence.predictor import get_prediction_scorecard
from src.intelligence.builder_tracker import get_prolific_builders, get_builder_stats
from src.intelligence.trend_tracker import get_category_sparklines
from src.feedback.taste_updater import get_taste_evolution
from src.delivery.telegram import send_telegram_message
from src.utils.logger import get_logger

log = get_logger("delivery.monthly_report")


async def generate_and_send_monthly_report():
    """Compile and send the monthly deep dive report."""
    log.info("generating_monthly_report")

    now = datetime.now(timezone.utc)
    # Report covers the previous month
    if now.month == 1:
        report_month = 12
        report_year = now.year - 1
    else:
        report_month = now.month - 1
        report_year = now.year

    month_str = f"{report_year}-{report_month:02d}"
    month_name = datetime(report_year, report_month, 1).strftime("%B %Y")

    # Load all items from the month
    items = _load_month_items(month_str)
    if not items:
        log.warning("no_data_for_monthly_report", month=month_str)
        return

    # Top 20 builds
    top_20 = sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:20]

    # Category distribution for the month
    cat_counts: dict[str, int] = {}
    for item in items:
        cat = item.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    # Total stats
    total_items = len(items)
    avg_score = sum(i.get("score", 0) for i in items) / max(len(items), 1)

    # Format report
    lines = [
        f"💊 <b>AI Monthly Deep Dive — {month_name}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🏆 <b>TOP 20 BUILDS OF THE MONTH:</b>",
    ]

    for i, item in enumerate(top_20, 1):
        title = _esc(item.get("title", "Unknown")[:60])
        score = item.get("score", 0)
        cat = item.get("category", "other")
        lines.append(f"{i}. <b>{title}</b> ⭐{score} [{cat}]")

    lines.extend([
        "",
        "📊 <b>CATEGORY BREAKDOWN:</b>",
    ])
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 10) + "░" * max(0, 10 - count)
        lines.append(f"  {cat}: {bar} {count}")

    # Biggest surprise — highest scored item from least expected category
    if len(top_20) >= 5:
        # Item with highest score from a category with fewest total items
        min_cat_count = min(cat_counts.values()) if cat_counts else 1
        surprise = None
        for item in top_20:
            if cat_counts.get(item.get("category", ""), 999) <= min_cat_count + 1:
                surprise = item
                break
        if surprise:
            lines.extend(["", "🎲 <b>BIGGEST SURPRISE:</b>",
                          f"  {_esc(surprise.get('title', '')[:70])} — came from nowhere in [{surprise.get('category', '')}]"])

    # Prolific builders of the month
    prolific = get_prolific_builders(min_appearances=2)
    if prolific:
        lines.extend(["", "👤 <b>TOP BUILDERS THIS MONTH:</b>"])
        for b in prolific[:5]:
            lines.append(f"  {_esc(b['name'])} — {b['appearances']} builds, avg ⭐{b['avg_score']}")

    # Prediction scorecard
    scorecard = get_prediction_scorecard()
    if scorecard:
        lines.extend(["", "🔮 <b>PREDICTION SCORECARD:</b>"])
        for batch in scorecard[-2:]:  # Show last 2 batches
            date = batch.get("date", "")
            for pred in batch.get("predictions", [])[:2]:
                status = "⏳" if not batch.get("scored") else "✅"
                lines.append(f"  {status} [{date}] {_esc(pred.get('prediction', '')[:80])}")

    # Taste evolution
    evolution = get_taste_evolution()
    monthly_interest = evolution.get("monthly_interest", {})
    if len(monthly_interest) >= 2:
        months = sorted(monthly_interest.keys())
        recent = months[-1]
        older = months[-2] if len(months) >= 2 else months[0]
        lines.extend(["", "🎯 <b>YOUR TASTE EVOLUTION:</b>",
                      f"  {older}: {', '.join(list(monthly_interest[older].keys())[:3])}",
                      f"  {recent}: {', '.join(list(monthly_interest[recent].keys())[:3])}"])

    # Category sparklines (visual trend)
    sparklines = get_category_sparklines(weeks=8)
    if sparklines:
        lines.extend(["", "📈 <b>CATEGORY TRENDS (8 weeks):</b>"])
        for cat, spark in sorted(sparklines.items(), key=lambda x: -len(x[1].replace("▁", "")))[:8]:
            lines.append(f"  {cat}: {spark}")

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total items: {total_items} | Avg score: {avg_score:.1f}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])

    text = "\n".join(lines)
    await send_telegram_message(text)
    log.info("monthly_report_sent", month=month_str)


def _load_month_items(month_str: str) -> list[dict]:
    """Load all items from a given month's logs."""
    month_dir = LOGS_DIR / month_str
    if not month_dir.exists():
        return []

    items = []
    for json_file in sorted(month_dir.glob("*.json")):
        if json_file.name == "alerts_today.json":
            continue
        try:
            with open(json_file, "r") as f:
                data = json.load(f)
            items.extend(data.get("items", []))
        except (json.JSONDecodeError, KeyError):
            continue

    return items


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
