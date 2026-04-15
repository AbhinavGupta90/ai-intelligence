"""
Monthly digest report generator.
Loads past month of daily logs and generates a comprehensive HTML report.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config import LOGS_DIR, KNOWLEDGE_DIR, FEEDBACK_PATH
from src.intelligence.predictor import get_prediction_scorecard
from src.intelligence.builder_tracker import get_prolific_builders, get_builder_stats
from src.intelligence.trend_tracker import get_category_sparklines
from src.feedback.taste_updater import get_taste_evolution
from src.delivery.telegram import send_telegram_message
from src.utils.logger import get_logger

log = get_logger("delivery.monthly_report")

async def generate_and_send_monthly_report():
    """
    Generate and send monthly report.

    Workflow:
    1. Load items from past month of daily logs
    2. Get top 20 items
    3. Get category sparklines (8 weeks back)
    4. Get prediction scorecard
    5. Get prolific builders
    6. Get builder stats
    7. Get taste evolution
    8. Format HTML report
    9. Send via Telegram
    """
    try:
        log.info("Generating monthly report")

        items = _load_month_items()
        log.info(f"Loaded {len(items)} items from past month")

        sparklines = get_category_sparklines(weeks_back=8)
        log.info(f"Generated sparklines for {len(sparklines)} categories")

        scorecard = get_prediction_scorecard()
        log.info(f"Prediction scorecard: {scorecard}")

        builders = get_prolific_builders(limit=20)
        log.info(f"Found {len(builders)} prolific builders")

        builder_stats = get_builder_stats()
        log.info(f"Builder stats: {builder_stats}")

        taste_evolution = get_taste_evolution()
        log.info(f"Taste evolution: {taste_evolution}")

        report_html = _format_monthly_report(
            items, sparklines, scorecard, builders, builder_stats, taste_evolution
        )

        await send_telegram_message(report_html)
        log.info("Sent monthly report via Telegram")

    except Exception as e:
        log.error(f"Failed to generate monthly report: {e}", exc_info=True)
        raise

def _load_month_items() -> list[dict]:
    """
    Load items from daily logs for the past month (30 days).

    Returns list of flattened items.
    """
    items = []
    now = datetime.now(timezone.utc)

    for i in range(30):
        date = now - timedelta(days=i)
        log_file = LOGS_DIR / f"{date.strftime('%Y-%m-%d')}.json"

        if not log_file.exists():
            continue

        try:
            with open(log_file, "r") as f:
                data = json.load(f)
                items.extend(data.get("items", []))
        except Exception as e:
            log.error(f"Failed to load {log_file}: {e}")

    return items

def _format_monthly_report(
    items: list[dict],
    sparklines: dict[str, list[int]],
    scorecard: dict,
    builders: list[dict],
    builder_stats: dict,
    taste_evolution: dict
) -> str:
    """
    Format monthly report as HTML for Telegram.

    Returns HTML string with:
    - Top 20 items of the month
    - Category evolution (sparklines)
    - Prediction scorecard
    - Top 15 builders
    - Builder statistics
    - Taste model evolution
    """
    # Sort items by score
    items_sorted = sorted(items, key=lambda x: x.get("final_score", 0), reverse=True)
    top_items = items_sorted[:20]

    html = "<b>Monthly Digest Report</b>\n\n"

    # Top items
    html += "<b>Top 20 Items of the Month (\U0001f3c6)</b>\n"
    for i, item in enumerate(top_items, 1):
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        score = item.get("final_score", 0)
        category = item.get("category", "General")
        html += f"{i}. [{category}] <a href=\"{url}\">{title}</a> (Score: {score:.1f})\n"
    html += "\n"

    # Category evolution (sparklines)
    html += "<b>Category Evolution (\U0001f4c8)</b>\n"
    for category, data in sorted(sparklines.items())[:10]:
        # Simple ASCII sparkline
        if data:
            min_val = min(data)
            max_val = max(data)
            if max_val > min_val:
                normalized = [int(((v - min_val) / (max_val - min_val)) * 8) for v in data]
                sparkline = "".join(["\u258f\u2590\u2591\u2592\u2593\u2594\u2595\u2596"[n] for n in normalized])
            else:
                sparkline = "~"
            avg = sum(data) / len(data)
            html += f"{category}: {sparkline} (avg: {avg:.1f})\n"
    html += "\n"

    # Prediction scorecard
    html += "<b>Prediction Performance (\U0001f52e)</b>\n"
    accuracy = scorecard.get("accuracy", 0)
    precision = scorecard.get("precision", 0)
    recall = scorecard.get("recall", 0)
    html += f"Accuracy: {accuracy:.1%}\n"
    html += f"Precision: {precision:.1%}\n"
    html += f"Recall: {recall:.1%}\n\n"

    # Top builders
    if builders:
        html += "<b>Top 15 Builders (\U0001f468\U0001f3fb\u200d\U0001f4bb)</b>\n"
        for i, builder in enumerate(builders[:15], 1):
            name = builder.get("name", "Unknown")
            count = builder.get("item_count", 0)
            html += f"{i}. {name} ({count} items)\n"
        html += "\n"

    # Builder statistics
    html += "<b>Builder Statistics (\U0001f4ca)</b>\n"
    html += f"Total builders: {builder_stats.get('total_builders', 0)}\n"
    html += f"New builders: {builder_stats.get('new_builders', 0)}\n"
    html += f"Active builders: {builder_stats.get('active_builders', 0)}\n"
    html += f"Avg items per builder: {builder_stats.get('avg_items', 0):.1f}\n\n"

    # Taste evolution
    html += "<b>Taste Model Evolution (\U0001f3af)</b>\n"
    current = taste_evolution.get("current", 0)
    previous = taste_evolution.get("previous", 0)
    change = current - previous
    direction = "\U0001f4c8" if change > 0 else "\U0001f4c9"
    html += f"Current accuracy: {current:.1%} {direction} ({change:+.1%} vs last month)\n"

    return html
