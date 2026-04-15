"""
Telegram delivery -- formats the daily digest and sends via Bot API.
Includes inline keyboard for feedback buttons (thumbs up/down).
"""

import json
import httpx
from datetime import datetime, timezone
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DELIVERY_CFG, MAX_DAILY_ITEMS
from src.utils.logger import get_logger

log = get_logger("delivery.telegram")

# Category emoji map
CAT_EMOJI = {
    "agent": "\U0001f916", "voice_ai": "\U0001f399\ufe0f", "dev_tool": "\U0001f6e0\ufe0f",
    "creative_ai": "\U0001f3a8", "infra": "\u2699\ufe0f", "research": "\U0001f52c",
    "local_llm": "\U0001f4bb", "multimodal": "\U0001f310", "robotics": "\U0001f9be",
    "other": "\U0001f4e6",
}

# Rank medals
RANK_EMOJI = {1: "\U0001f3c6", 2: "\U0001f948", 3: "\U0001f949"}


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_daily_digest(
    items: list[dict],
    pipeline_stats: dict,
    category_counts: dict,
    velocity_alerts: int,
    taste_accuracy: float | None = None,
) -> str:
    """Format the daily digest as an HTML message for Telegram."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %d, %Y")

    lines = [
        f"\U0001f9e0 <b>AI Intelligence Brief -- {date_str}</b>",
        "",
    ]

    # Top items
    display_items = items[:MAX_DAILY_ITEMS]
    for i, item in enumerate(display_items, 1):
        rank = RANK_EMOJI.get(i, f"#{i}")
        cat = item.get("category", "other")
        cat_emoji = CAT_EMOJI.get(cat, "\U0001f4e6")
        score = item.get("score", 0)
        title = _escape_html(item.get("title", "Unknown")[:80])
        summary = _escape_html(item.get("summary", "")[:200])
        why = _escape_html(item.get("why_interesting", "")[:150])
        url = item.get("url", "")
        builder = item.get("builder_type", "unknown")
        velocity_flag = item.get("velocity_flag", False)

        lines.append(f"{rank} {cat_emoji} <b>{title}</b>")
        lines.append(f"   Score: {score}/10  |  {cat}  |  {builder}")
        if summary:
            lines.append(f"   {summary}")
        if why:
            lines.append(f"   Why: {why}")

        # Links line
        link_parts = []
        if url:
            link_parts.append(f'<a href="{url}">Link</a>')
        if velocity_flag:
            link_parts.append("TRENDING")
        if link_parts:
            lines.append("   " + " | ".join(link_parts))
        lines.append("")

    # Category summary
    if category_counts:
        cat_parts = []
        for cat_name, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            emoji = CAT_EMOJI.get(cat_name, "\U0001f4e6")
            cat_parts.append(f"{emoji} {cat_name}: {count}")
        lines.append("<b>Categories:</b> " + " | ".join(cat_parts))
        lines.append("")

    # Footer
    lines.extend(_format_digest_footer(pipeline_stats, velocity_alerts, taste_accuracy))

    return "\n".join(lines)


def _format_digest_footer(
    pipeline_stats: dict,
    velocity_alerts: int,
    taste_accuracy: float | None = None,
) -> list[str]:
    """Format the footer section with pipeline stats."""
    lines = []
    lines.append("")

    fetched = pipeline_stats.get("fetched", 0)
    scored = pipeline_stats.get("scored", 0)
    delivered = pipeline_stats.get("delivered", 0)
    duration = pipeline_stats.get("duration_seconds", 0)

    lines.append(f"<b>Pipeline:</b> {fetched} fetched -> {scored} scored -> {delivered} delivered ({duration:.1f}s)")

    if velocity_alerts > 0:
        lines.append(f"Velocity alerts: {velocity_alerts} trending items detected")

    if taste_accuracy is not None:
        lines.append(f"Taste model accuracy: {taste_accuracy:.0%}")

    source_stats = pipeline_stats.get("source_stats", {})
    if source_stats:
        parts = []
        for src, count in sorted(source_stats.items(), key=lambda x: -x[1]):
            parts.append(f"{src}: {count}")
        lines.append("<b>Sources:</b> " + ", ".join(parts))

    lines.append("")
    lines.append("<i>Powered by AI Intelligence Digest</i>")
    return lines


def format_alert(item: dict) -> str:
    """Format a single velocity alert item for Telegram."""
    title = _escape_html(item.get("title", "Unknown")[:80])
    score = item.get("score", 0)
    source = item.get("source", "unknown")
    url = item.get("url", "")
    why = _escape_html(item.get("why_interesting", "")[:200])

    lines = [
        f"ALERT <b>{title}</b>",
        f"Score: {score}/10 | Source: {source}",
    ]
    if why:
        lines.append(f"Why: {why}")
    if url:
        lines.append(f'<a href="{url}">Read more</a>')
    return "\n".join(lines)


async def send_telegram_message(
    text: str,
    with_feedback: bool = False,
    item_ids: list[str] | None = None,
) -> dict | None:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not configured, skipping send")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    # Add inline keyboard for feedback if requested
    if with_feedback and item_ids:
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Good digest", "callback_data": json.dumps({"action": "feedback", "value": "good", "ids": item_ids[:5]})[:64]},
                    {"text": "Too noisy", "callback_data": json.dumps({"action": "feedback", "value": "noisy"})[:64]},
                ]
            ]
        }
        payload["reply_markup"] = json.dumps(keyboard)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            log.info("Telegram message sent", message_id=result.get("result", {}).get("message_id"))
            return result
    except httpx.HTTPStatusError as e:
        log.error("Telegram API error", status=e.response.status_code, body=e.response.text[:500])
        return None
    except Exception as e:
        log.error("Failed to send Telegram message", error=str(e))
        return None


async def send_daily_digest(
    items: list[dict],
    pipeline_stats: dict,
    category_counts: dict | None = None,
    velocity_alerts: int = 0,
    taste_accuracy: float | None = None,
) -> dict | None:
    """Format and send the daily digest to Telegram."""
    if not items:
        log.warning("No items to send in daily digest")
        return await send_telegram_message("No noteworthy AI items found today.")

    if category_counts is None:
        category_counts = {}
        for item in items:
            cat = item.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1

    text = format_daily_digest(items, pipeline_stats, category_counts, velocity_alerts, taste_accuracy)
    item_ids = [item.get("item_id", "") for item in items[:MAX_DAILY_ITEMS]]

    # Split long messages (Telegram limit is 4096 chars)
    if len(text) <= 4096:
        return await send_telegram_message(text, with_feedback=True, item_ids=item_ids)

    # Send in chunks
    chunks = _split_message(text, 4096)
    result = None
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        result = await send_telegram_message(chunk, with_feedback=is_last, item_ids=item_ids if is_last else None)
    return result


async def send_alert(item: dict) -> dict | None:
    """Format and send a single velocity alert."""
    text = format_alert(item)
    return await send_telegram_message(text)


def _format_single_item(rank: int, item: dict) -> str:
    """Format a single item for display in the digest."""
    rank_str = RANK_EMOJI.get(rank, f"#{rank}")
    cat = item.get("category", "other")
    cat_emoji = CAT_EMOJI.get(cat, "\U0001f4e6")
    title = _escape_html(item.get("title", "Unknown")[:80])
    score = item.get("score", 0)
    url = item.get("url", "")

    line = f"{rank_str} {cat_emoji} <b>{title}</b> ({score}/10)"
    if url:
        line += f' - <a href="{url}">Link</a>'
    return line


def _split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split a long message into chunks at line boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks
