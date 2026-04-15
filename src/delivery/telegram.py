"""
Telegram delivery for AI Daily Digest.
Formats and sends the daily digest via Telegram Bot API.
"""

import os
import logging
import asyncio
import aiohttp
from datetime import datetime, timezone

log = logging.getLogger("telegram")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Emojis aligned with main.py _CATEGORY_PATTERNS ──
CAT_EMOJI = {
    "AI/ML": "\U0001f916",        # 🤖
    "Dev Tools": "\U0001f6e0\ufe0f",  # 🛠️
    "Product Launch": "\U0001f680",    # 🚀
    "Funding": "\U0001f4b0",          # 💰
    "Research": "\U0001f52c",          # 🔬
    "Cloud/Infra": "\u2601\ufe0f",     # ☁️
    "Crypto/Web3": "\U0001fa99",       # 🪙
    "Security": "\U0001f6e1\ufe0f",    # 🛡️
    "General": "\U0001f4e6",           # 📦
}

RANK_EMOJI = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}  # 🥇🥈🥉

SOURCE_LABELS = {
    "hackernews": "Hacker News",
    "github_trending": "GitHub Trending",
    "arxiv": "arXiv",
    "devto": "Dev.to",
    "reddit": "Reddit",
    "producthunt": "Product Hunt",
    "huggingface": "HuggingFace",
    "twitter": "Twitter/X",
    "youtube": "YouTube",
}


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _score_bar(score: float) -> str:
    """Visual score indicator using filled/empty blocks."""
    filled = round(score)
    empty = 10 - filled
    return "\u2588" * filled + "\u2591" * empty


def _format_item(rank: int, item: dict) -> str:
    """Format a single digest item as a readable Telegram message block."""
    # Rank emoji or number
    rank_str = RANK_EMOJI.get(rank, f"<b>#{rank}</b>")

    # Category emoji
    cat = item.get("category", "General")
    cat_emoji = CAT_EMOJI.get(cat, "\U0001f4e6")

    # Title (truncate at 100 chars)
    title = _escape_html(item.get("title", "Untitled")[:100])

    # URL — clickable title
    url = item.get("url", "")
    if url:
        title_line = f'{rank_str} {cat_emoji} <a href="{url}">{title}</a>'
    else:
        title_line = f"{rank_str} {cat_emoji} <b>{title}</b>"

    # Score bar
    score = item.get("final_score", item.get("score", 0))
    score_line = f"   {_score_bar(score)} {score}/10"

    # Source label
    source_raw = item.get("source", "")
    source_name = SOURCE_LABELS.get(source_raw, source_raw.replace("_", " ").title())
    meta_parts = [cat]
    if source_name:
        meta_parts.append(f"via {source_name}")
    separator = " \u2022 "
    meta_line = f"   {separator.join(meta_parts)}"

    # Summary (first 150 chars)
    summary = item.get("summary", "") or item.get("description", "")
    if summary:
        summary = _escape_html(summary[:150].strip())
        if len(item.get("summary", "") or item.get("description", "")) > 150:
            summary += "..."

    lines = [title_line, score_line, meta_line]
    if summary:
        lines.append(f"   {summary}")

    return "\n".join(lines)


def format_daily_digest(
    items: list,
    pipeline_stats: dict = None,
    category_counts: dict = None,
    velocity_alerts: int = 0,
    taste_accuracy: float = None,
) -> str:
    """Format the complete daily digest message for Telegram."""
    if not items:
        return "\U0001f4ed <b>AI Daily Digest</b>\n\nNo stories matched your filters today. Check back tomorrow!"

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%B %d, %Y")

    lines = []

    # ── Header ──
    lines.append(f"\U0001f4f0 <b>AI Daily Digest</b>  \u2014  {date_str}")
    lines.append(f"\U0001f4ca {len(items)} top stories curated for you")
    lines.append("")

    # ── Pipeline summary (compact) ──
    if pipeline_stats:
        raw = pipeline_stats.get("raw_count", "?")
        filtered = pipeline_stats.get("filtered_count", "?")
        sources_ok = pipeline_stats.get("sources_ok", "?")
        sources_total = pipeline_stats.get("sources_total", "?")
        lines.append(
            f"\u2699\ufe0f {sources_ok}/{sources_total} sources \u2022 "
            f"{raw} fetched \u2192 {filtered} filtered \u2192 {len(items)} delivered"
        )
        lines.append("")

    # ── Category breakdown (one line) ──
    if category_counts:
        cat_parts = []
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            emoji = CAT_EMOJI.get(cat, "\U0001f4e6")
            cat_parts.append(f"{emoji}{count}")
        lines.append(" ".join(cat_parts))
        lines.append("")

    # ── Separator ──
    lines.append("\u2500" * 20)
    lines.append("")

    # ── Items ──
    for i, item in enumerate(items, 1):
        lines.append(_format_item(i, item))
        lines.append("")  # blank line between items

    # ── Footer ──
    lines.append("\u2500" * 20)
    lines.append("\U0001f916 <i>Curated by AI Daily Digest Pipeline</i>")
    lines.append("\U0001f517 <i>Tap any headline to read the full story</i>")

    return "\n".join(lines)


async def _send_telegram_message(text: str, session: aiohttp.ClientSession) -> bool:
    """Send a single message via Telegram Bot API. Returns True on success."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
            if not data.get("ok"):
                log.error(f"Telegram API error: {data.get('description', 'unknown')}")
                return False
            return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split a long message into chunks that fit Telegram's 4096 char limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        # +1 for the newline character
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current.rstrip("\n"))
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip("\n"))
    return chunks


async def send_daily_digest(
    items: list,
    pipeline_stats: dict = None,
    category_counts: dict = None,
    velocity_alerts: int = 0,
    taste_accuracy: float = None,
) -> bool:
    """Format and send the daily digest to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    message = format_daily_digest(
        items,
        pipeline_stats=pipeline_stats,
        category_counts=category_counts,
        velocity_alerts=velocity_alerts,
        taste_accuracy=taste_accuracy,
    )

    chunks = _split_message(message)
    log.info(f"Sending digest: {len(items)} items in {len(chunks)} message(s)")

    success = True
    async with aiohttp.ClientSession() as session:
        for i, chunk in enumerate(chunks):
            ok = await _send_telegram_message(chunk, session)
            if not ok:
                log.error(f"Failed to send chunk {i+1}/{len(chunks)}")
                success = False
            if i < len(chunks) - 1:
                await asyncio.sleep(1)  # rate limit between chunks

    return success
