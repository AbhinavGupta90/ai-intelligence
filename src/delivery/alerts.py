"""
Real-time breakthrough alerts — for items scoring 9.5+ or extreme velocity.
Runs every 4 hours, max 2 alerts per day.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from src.config import MIN_SCORE_ALERT, MAX_REALTIME_ALERTS, LOGS_DIR
from src.delivery.telegram import send_alert
from src.utils.logger import get_logger

log = get_logger("delivery.alerts")

ALERTS_SENT_FILE = LOGS_DIR / "alerts_today.json"


async def check_and_send_alerts(scored_items: list[dict]):
    """
    Check for breakthrough items and send real-time alerts.
    Respects daily alert limit to avoid spam.
    """
    alerts_sent = _load_alerts_sent_today()

    if len(alerts_sent) >= MAX_REALTIME_ALERTS:
        log.info("alert_limit_reached", sent=len(alerts_sent), max=MAX_REALTIME_ALERTS)
        return

    # Find items above alert threshold
    alert_candidates = [
        item for item in scored_items
        if item.get("score", 0) >= MIN_SCORE_ALERT
        and item.get("item_id") not in alerts_sent
    ]

    # Sort by score, take only what budget allows
    alert_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    remaining_budget = MAX_REALTIME_ALERTS - len(alerts_sent)
    to_send = alert_candidates[:remaining_budget]

    for item in to_send:
        log.info("sending_alert", title=item.get("title", "")[:50], score=item.get("score", 0))
        await send_alert(item)
        alerts_sent.add(item["item_id"])

    _save_alerts_sent(alerts_sent)

    if to_send:
        log.info("alerts_sent", count=len(to_send))


def _load_alerts_sent_today() -> set:
    """Load the set of item IDs that received alerts today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not ALERTS_SENT_FILE.exists():
        return set()

    try:
        with open(ALERTS_SENT_FILE, "r") as f:
            data = json.load(f)

        if data.get("date") != today:
            # New day — reset
            return set()

        return set(data.get("item_ids", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def _save_alerts_sent(item_ids: set):
    """Save the set of alerted item IDs."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = {"date": today, "item_ids": list(item_ids)}

    with open(ALERTS_SENT_FILE, "w") as f:
        json.dump(data, f)
