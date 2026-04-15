"""
Weekly digest report generator.
Loads past 7 days of daily logs and generates a comprehensive HTML report.
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
    """
    Generate and send weekly report.

    Workflow:
    1. Load items from past 7 days of daily logs
    2. Get trending categories
    3. Get prolific builders
    4. Get rising builders
    5. Get breakout projects
    6. Generate predictions
    7. Get taste accuracy
    8. Format HTML report
    9. Send via Telegram
    """
    try:
        log.info("Generating weekly report")

        items = _load_week_items(days=7)
        log.info(f"Loaded {len(items)} items from past 7 days")

        trends = get_trending_categories()
        log.info(f"Found {len(trends.get('rising', []))} rising categories")

        builders = get_prolific_builders(limit=10)
        log.info(f"Found {len(builders)} prolific builders")

        rising = get_rising_builders(limit=10)
        log.info(f"Found {len(rising)} rising builders")

        projects = get_breakout_projects(days=7)
        log.info(f"Found {len(projects)} breakout projects")

        predictions = generate_predictions(items, horizon_days=7)
        log.info(f"Generated {len(predictions)} predictions")

        taste_acc = get_taste_accuracy()
        log.info(f"Taste accuracy: {taste_acc}")

        report_html = _format_weekly_report(
            items, trends, builders, rising, projects, predictions, taste_acc
        )

        await send_telegram_message(report_html)
        log.info("Sent weekly report via Telegram")

    except Exception as e:
        log.error(f"Failed to generate weekly report: {e}", exc_info=True)
        raise

def _load_week_items(days=7) -> list[dict]:
    """
    Load items from daily logs for the past N days.

    Returns list of flattened items (each item is a dict with score, title, url, etc.).
    """
    items = []
    now = datetime.now(timezone.utc)

    for i in range(days):
        date = now - timedelta(days=i)
        log_file = LOGS_DIR / f"{date.strftime('%Y-%m-%d')}.json"

        if not log_file.exists():
            log.warning(f"Daily log not found: {log_file}")
            continue

        try:
            with open(log_file, "r") as f:
                data = json.load(f)
                # data is {"items": [...], "stats": {...}}
                items.extend(data.get("items", []))
        except Exception as e:
            log.error(f"Failed to load {log_file}: {e}")

    return items

def _format_weekly_report(
    items: list[dict],
    trends: dict,
    builders: list[dict],
    rising: list[dict],
    projects: list[dict],
    predictions: list[dict],
    taste_accuracy: float
) -> str:
    """
    Format weekly report as HTML for Telegram.

    Returns HTML string with:
    - Top 10 items of the week
    - Category trends (rising, declining, new, hot streak)
    - Prolific builders
    - Rising builders
    - Breakout projects
    - Predictions
    - Taste accuracy
    """
    # Sort items by score
    items_sorted = sorted(items, key=lambda x: x.get("final_score", 0), reverse=True)
    top_items = items_sorted[:10]

    html = "<b>Weekly Digest Report</b>\n\n"

    # Top items
    html += "<b>Top Items of the Week (\U0001f525)</b>\n"
    for i, item in enumerate(top_items, 1):
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        score = item.get("final_score", 0)
        html += f"{i}. <a href=\"{url}\">{title}</a> (Score: {score:.1f})\n"
    html += "\n"

    # Category trends
    html += "<b>Category Trends (\U0001f4ca)</b>\n"
    rising_cats = trends.get("rising", [])
    declining_cats = trends.get("declining", [])
    new_cats = trends.get("new", [])
    hot_streak = trends.get("hot_streak")

    if rising_cats:
        html += f"Rising: {', '.join(rising_cats[:5])}\n"
    if declining_cats:
        html += f"Declining: {', '.join(declining_cats[:5])}\n"
    if new_cats:
        html += f"New: {', '.join(new_cats[:5])}\n"
    if hot_streak:
        html += f"Hot streak: {hot_streak}\n"
    html += "\n"

    # Prolific builders
    if builders:
        html += "<b>Top Builders (\U0001f468\U0001f3fb\u200d\U0001f4bb)</b>\n"
        for builder in builders[:5]:
            name = builder.get("name", "Unknown")
            count = builder.get("item_count", 0)
            html += f"- {name} ({count} items)\n"
        html += "\n"

    # Rising builders
    if rising:
        html += "<b>Rising Builders (\U0001f3ad)</b>\n"
        for builder in rising[:5]:
            name = builder.get("name", "Unknown")
            trend = builder.get("trend", 0)
            html += f"- {name} (trend: {trend:+.1f})\n"
        html += "\n"

    # Breakout projects
    if projects:
        html += "<b>Breakout Projects (\U0001f681)</b>\n"
        for proj in projects[:5]:
            name = proj.get("name", "Unknown")
            momentum = proj.get("momentum", 0)
            html += f"- {name} (momentum: {momentum:.1f})\n"
        html += "\n"

    # Predictions
    if predictions:
        html += "<b>Predictions for Next Week (\U0001f52e)</b>\n"
        for pred in predictions[:5]:
            category = pred.get("category", "Unknown")
            confidence = pred.get("confidence", 0)
            direction = "\U0001f4c8" if pred.get("direction") == "up" else "\U0001f4c9"
            html += f"{direction} {category} (confidence: {confidence:.0%})\n"
        html += "\n"

    # Taste accuracy
    html += f"<b>Taste Model Accuracy (\U0001f3af)</b>: {taste_accuracy:.1%}\n"

    return html
