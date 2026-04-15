"""
Telegram feedback handler — processes thumbs up/down callbacks.
Can run as a standalone bot or integrated into the main pipeline.
"""

import json
import asyncio
from datetime import datetime, timezone
from src.config import TELEGRAM_BOT_TOKEN, FEEDBACK_PATH
from src.utils.logger import get_logger

log = get_logger("feedback.handler")


def save_feedback(item_id: str, is_positive: bool, item_metadata: dict | None = None):
    """Save a single feedback entry to feedback.json."""
    data = _load_feedback()
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "item_id": item_id,
        "date": now,
        "category": (item_metadata or {}).get("category", "unknown"),
        "keywords": (item_metadata or {}).get("tags", []),
        "builder_type": (item_metadata or {}).get("builder_type", "unknown"),
        "score": (item_metadata or {}).get("score", 0),
    }

    if is_positive:
        data.setdefault("thumbs_up", []).append(entry)
    else:
        data.setdefault("thumbs_down", []).append(entry)

    _save_feedback(data)
    log.info("feedback_saved", item_id=item_id, positive=is_positive)


def get_taste_accuracy() -> float | None:
    """
    Calculate taste accuracy = % of delivered items that got thumbs up.
    Returns None if not enough data.
    """
    data = _load_feedback()
    ups = len(data.get("thumbs_up", []))
    downs = len(data.get("thumbs_down", []))
    total = ups + downs

    if total < 5:
        return None

    return ups / total


async def run_feedback_bot():
    """
    Run a long-polling Telegram bot to handle feedback callbacks.
    This is meant to be deployed as a separate always-on process.
    """
    if not TELEGRAM_BOT_TOKEN:
        log.error("no_bot_token", msg="TELEGRAM_BOT_TOKEN not set")
        return

    import httpx

    log.info("feedback_bot_starting")
    offset = 0

    async with httpx.AsyncClient() as client:
        while True:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                resp = await client.get(url, params={"offset": offset, "timeout": 30}, timeout=35)
                data = resp.json()

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    callback = update.get("callback_query")

                    if callback:
                        cb_data = callback.get("data", "")
                        cb_id = callback.get("id", "")

                        # Per-item feedback: "up_<item_id>" or "dn_<item_id>"
                        if cb_data.startswith("up_"):
                            item_id = cb_data[3:]
                            save_feedback(item_id, is_positive=True)
                            await _answer_callback(client, cb_id, "👍 Got it! Learning your taste.")
                        elif cb_data.startswith("dn_"):
                            item_id = cb_data[3:]
                            save_feedback(item_id, is_positive=False)
                            await _answer_callback(client, cb_id, "👎 Noted. Adjusting future picks.")

            except Exception as e:
                log.warning("polling_error", error=str(e))
                await asyncio.sleep(5)


async def _answer_callback(client, callback_id: str, text: str):
    """Acknowledge a Telegram callback query."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        await client.post(url, json={"callback_query_id": callback_id, "text": text})
    except Exception as e:
        log.warning("callback_answer_failed", error=str(e))


def _load_feedback() -> dict:
    if not FEEDBACK_PATH.exists():
        return {"thumbs_up": [], "thumbs_down": [], "taste_profile": {}}
    try:
        with open(FEEDBACK_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return {"thumbs_up": [], "thumbs_down": [], "taste_profile": {}}


def _save_feedback(data: dict):
    with open(FEEDBACK_PATH, "w") as f:
        json.dump(data, f, indent=2)
