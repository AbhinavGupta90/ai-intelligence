"""
Standalone feedback bot — deploy to Railway/Render for always-on feedback collection.
Handles Telegram inline button callbacks (👍/👎) and saves to feedback.json.

Deployment:
  Railway: `railway up` (auto-detects Python, runs this file)
  Render:  Set start command to `python run_bot.py`
  Docker:  `python run_bot.py`

Environment variables needed:
  TELEGRAM_BOT_TOKEN — your bot token from @BotFather

Optional (for richer feedback data):
  None — feedback handler reads item metadata from daily logs if available.
"""

import asyncio
import os
import sys
import json
import signal
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.logger import setup_logging, get_logger

setup_logging()
log = get_logger("feedback_bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
FEEDBACK_PATH = Path(__file__).parent / "feedback.json"

# Graceful shutdown
shutdown_event = asyncio.Event()


def handle_signal(sig, frame):
    log.info("shutdown_requested", signal=sig)
    shutdown_event.set()


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def load_feedback() -> dict:
    if not FEEDBACK_PATH.exists():
        return {"thumbs_up": [], "thumbs_down": [], "taste_profile": {}}
    try:
        with open(FEEDBACK_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return {"thumbs_up": [], "thumbs_down": [], "taste_profile": {}}


def save_feedback_entry(item_id: str, is_positive: bool):
    data = load_feedback()
    entry = {
        "item_id": item_id,
        "date": datetime.now(timezone.utc).isoformat(),
        "category": "unknown",  # Will be enriched by taste_updater
        "keywords": [],
        "builder_type": "unknown",
        "score": 0,
    }

    # Try to enrich from recent daily logs
    enriched = _lookup_item_metadata(item_id)
    if enriched:
        entry.update(enriched)

    if is_positive:
        data.setdefault("thumbs_up", []).append(entry)
    else:
        data.setdefault("thumbs_down", []).append(entry)

    with open(FEEDBACK_PATH, "w") as f:
        json.dump(data, f, indent=2)

    log.info("feedback_saved", item_id=item_id, positive=is_positive)


def _lookup_item_metadata(item_id: str) -> dict | None:
    """Try to find item metadata in recent daily logs for richer feedback data."""
    logs_dir = Path(__file__).parent / "logs"
    if not logs_dir.exists():
        return None

    # Check last 3 days of logs
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    for day_offset in range(3):
        date = now - timedelta(days=day_offset)
        month_dir = logs_dir / date.strftime("%Y-%m")
        json_path = month_dir / f"{date.strftime('%Y-%m-%d')}.json"

        if not json_path.exists():
            continue

        try:
            with open(json_path, "r") as f:
                log_data = json.load(f)
            for item in log_data.get("items", []):
                if item.get("item_id", "").startswith(item_id) or item_id in item.get("item_id", ""):
                    return {
                        "category": item.get("category", "unknown"),
                        "keywords": item.get("tags", []),
                        "builder_type": item.get("builder_type", "unknown"),
                        "score": item.get("score", 0),
                    }
        except (json.JSONDecodeError, KeyError):
            continue

    return None


async def run():
    """Main bot loop — long-polling for Telegram updates."""
    if not TELEGRAM_BOT_TOKEN:
        log.error("no_token", msg="Set TELEGRAM_BOT_TOKEN environment variable")
        sys.exit(1)

    import httpx

    log.info("bot_starting", msg="Feedback bot is live. Listening for callbacks...")
    offset = 0

    async with httpx.AsyncClient() as client:
        while not shutdown_event.is_set():
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                resp = await client.get(
                    url,
                    params={"offset": offset, "timeout": 30},
                    timeout=35,
                )
                data = resp.json()

                if not data.get("ok"):
                    log.warning("api_error", response=data)
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    callback = update.get("callback_query")

                    if not callback:
                        continue

                    cb_data = callback.get("data", "")
                    cb_id = callback.get("id", "")
                    user = callback.get("from", {}).get("first_name", "User")

                    if cb_data.startswith("up_"):
                        item_id = cb_data[3:]
                        save_feedback_entry(item_id, is_positive=True)
                        await _answer(client, cb_id, f"👍 Thanks {user}! Taste updated.")
                        log.info("thumbs_up", item_id=item_id, user=user)

                    elif cb_data.startswith("dn_"):
                        item_id = cb_data[3:]
                        save_feedback_entry(item_id, is_positive=False)
                        await _answer(client, cb_id, f"👎 Noted {user}. Adjusting picks.")
                        log.info("thumbs_down", item_id=item_id, user=user)

            except httpx.ReadTimeout:
                # Normal for long-polling — just retry
                continue
            except Exception as e:
                log.warning("poll_error", error=str(e))
                await asyncio.sleep(5)

    log.info("bot_stopped")


async def _answer(client, callback_id: str, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        await client.post(url, json={"callback_query_id": callback_id, "text": text})
    except Exception:
        pass


if __name__ == "__main__":
    print("🤖 AI Intelligence Feedback Bot")
    print("   Listening for 👍/👎 callbacks...")
    print("   Press Ctrl+C to stop.\n")
    asyncio.run(run())
