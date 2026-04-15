"""
Telegram delivery â€” formats the daily digest and sends via Bot API.
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
    "agent": "ğŸ¤–", "voice_ai": "ğŸ™ï¸", "dev_tool": "ğŸ› ï¸", "creative_ai": "ğŸ¨",
    "infra": "âš™ï¸", "research": "ğŸ”¬", "local_llm": "ğŸ’»", "multimodal": "ğŸŒ",
    "robotics": "ğŸ¦¾", "other": "ğŸ“¦",
}

# Rank medals
RANK_EMOJI = {1: "ğŸ†", 2: "ğŸ¥ˆ", 3: "ğŸ¥‰"}


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
        f"ğŸ§  <b>AI Intelligence Brief â€” {date_str}</b>",
        "â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”",
        "",
    ]

    # Top items
    display_items = items[:MAX_DAILY_ITEMS]
    for i, item in enumerate(display_items, 1):
        rank = RANK_EMOJI.get(i, f"#{i}")
        cat = item.get("category", "other")
        cat_emoji = CAT_EMOJI.get(cat, "ğŸ“¦")
        score = item.get("score", 0)
        title = _escape_html(item.get("title", "Unknown")[:80])
        summary = _escape_html(item.get("summary", "")[:200])
        why = _escape_html(item.get("why_interesting", "")[:150])
        url = item.get("url", "")
        ext_url = item.get("external_url", "")
        builder = item.get("builder_type", "unknown")
        velocity_flag = item.get("velocity_flag", False)

        lines.append(f"{rank} â€”  <b>{title}</b> ã€Œ{catë5 â­ {score}")
        if summary:
            lines.append(f"ğŸ“ {summary}")
        if why:
            lines.append(f"ğŸ’¡ {why}")

        # Links line
        link_parts = [f'<a href="{url}">ğŸ”— Link</a>']
        if ext_url and ext_url != url:
            link_parts.append(f'<a href="{ext_url}">ğŸ¯ Demo</a>')
        if item.get("is_open_source"):
            link_parts.append("ğŸ“‚ Open Source")
        link_parts.append(f"ğŸ‘¤ {builder.title()}")
        lines.append(" | ".join(link_parts))

        if velocity_flag:
            eng = item.get("engagement", 0)
            age = round(item.get("velocity", 0), 1)
            lines.append(f"ğŸš€ <b>Velocity Alert:</b> {eng} engagement, velocity {age}/hr")

        lines.append("")
        lines.append("â”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆâ”ˆŠJ        lines.append("")

    # Category map
    lines.append("â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”")
    lines.append("")
    lines.append("ğŸ“Š <b>Today's Category Map:</b>")
    cat_line_parts = []
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        bar = "â–ˆ" * min(count, 5) + "â–‘" * max(0, 5 - count)
        emoji = CAT_EMOJI.get(cat, "ğŸ“¦")
        cat_line_parts.append(f"{emoji} {cat}: {bar} {count}")
    lines.append("\n".join(cat_line_parts))
    lines.append("")

    # Velocity alerts count
    if velocity_alerts > 0:
        lines.append(f"ğŸš€ <b>Velocity Alerts:</b> {velocity_alerts} posts blowing up right now")
        lines.append("")

    # Pipeline stats
    scanned = pipeline_stats.get("total_scanned", 0)
    filtered = pipeline_stats.get("pre_filtered", 0)
    scored = pipeline_stats.get("llm_scored", 0)
    delivered = pipeline_stats.get("delivered", 0)
    sources_ok = pipeline_stats.get("sources_active", 0)
    sources_total = pipeline_stats.get("sources_total", 0)
    source_errors = pipeline_stats.get("source_errors", [])

    lines.append("â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”")
    lines.append(f"âš™ï¸ Pipeline: {scanned:,} scanned â†’ {filtered} pre-filtered â†’ {scored} scored â†’ {delivered} delivered")

    source_status = f"ğŸ“¡ Sources: {sources_ok}/{sources_total} âœ…"
    if source_errors:
        source_status += " | " + " | ".join(fâœŒ" for s in source_errors)
    lines.append(source_status)

    if taste_accuracy is not None:
        lines.append(f"ğŸ¯Â  Taste Match: {taste_accuracy:.0%} (based on your feedback history)")

    lines.append("â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”")

    # Check for fallback scoring
    if any(item.get("_fallback") for item in display_items):
        lines.append("")
        lines.append("âš ï¸ <i>AI scoring unavailable â€” items ranked by engagement only</i>")

    return "\n".join(lines)


def format_alert(item: dict) -> str:
    """Format a real-time breakthrough alert message."""
    title = _escape_html(item.get("title", "Unknown")[:100])
    summary = _escape_html(item.get("summary", "")[:200])
    url = item.get("url", "")
    score = item.get("score", 0)

    return (
        f"ğŸš¨ <b>BREAKING BUILD</b> â­ {score}\n\n"
        f"<b>{title}</b>\n"
        f"{summary}\n\n"
        f'<a href="{url}">ğŸ”— Check it out</a>'
    )


async def send_telegram_message(text: str, with_feedback: bool = False, item_ids: list[str] | None = None):
    """Send a message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("telegram_not_configured", msg="Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        print("\n" + "=" * 60)
        print("TELEGRAM MESSAGE (dry run / not configured):")
        print("=" * 60)
        # Strip HTML tags for console output
        import re
        clean = re.sub(r"<[^>]+>", "", text)
        print(clean)
        print("=" * 60 + "\n")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    parse_mode = DELIVERY_CFG.get("telegram", {}).get("parse_mode", "HTML")

    # Split long messages (Telegram limit is 4096 chars)
    chunks = _split_message(text, max_len=4000)

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": DELIVERY_CFG.get("telegram", {}).get("disable_preview", True),
        }

        # Add feedback buttons to the last chunk
        if with_feedback and i == len(chunks) - 1 and item_ids:
            keyboard = _build_feedback_keyboard(item_ids)
            if keyboard:
                payload["reply_markup"] = json.dumps(keyboard)

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, timeout=30)
                resp.raise_for_status()
                log.info("telegram_sent", chunk=i + 1, total=len(chunks))
            except Exception as e:
                log.error("telegram_send_failed", chunk=i + 1, error=str(e))


async def send_daily_digest(
    items: list[dict],
    pipeline_stats: dict,
    category_counts: dict,
    velocity_alerts: int,
    taste_accuracy: float | None = None,
):
    """
    Format and send the complete daily digest.
    Sends each item as a separate message with per-item ğŸ‘/ğŸ‘ buttons,
    then a footer message with stats.
    """
    display_items = items[:MAX_DAILY_ITEMS]

    # â”€â”€ Header message â”€â”€
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %d, %Y")
    header = (
        f"ğŸ§  <b>AI Intelligence Brief â€” {date_str}</b>\n"
        f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
        f"âš™ï¸ {pipeline_stats.get('total_scanned', 0):,} scanned â†’ {len(display_items)} gems\n"
        f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”"
    )
    await send_telegram_message(header)

    # â”€â”€ Individual item messages with per-item feedback â”€â”€
    for i, item in enumerate(display_items, 1):
        item_msg = _format_single_item(i, item)
        item_id = item.get("item_id", "")
        keyboard = _build_item_feedback_keyboard(item_id)

        await _send_with_keyboard(item_msg, keyboard)

    # â”€â”€ Footer with stats â”€â”€
    footer = _format_digest_footer(
        pipeline_stats, category_counts, velocity_alerts, taste_accuracy, display_items
    )
    await send_telegram_message(footer)


async def send_alert(item: dict):
    """Send a real-time breakthrough alert."""
    text = format_alert(item)
    await send_telegram_message(text, with_feedback=True, item_ids=[item.get("item_id", "")])


def _format_single_item(rank: int, item: dict) -> str:
   """Format a single digest item for its own Telegram message."""
    rank_emoji = RANK_EMOJI.get(rank, f"#{rank}")
    cat = item.get("category", "other")
    cat_emoji = CAT_EMOJJ.get(cat, "ğŸ“¦")
    score = item.get("score", 0)
    title = _escape_html(item.get("title", "Unknown")[:80])
    summary = _escape_html(item.get("summary", "")[:200])
    why = _escape_html(item.get("why_interesting", "")[:150])
    url = item.get("url", "")
    ext_url = item.get("external_url", "")
    builder = item.get("builder_type", "unknown")
    velocity_flag = item.get("velocity_flag", False)

    lines = [f"{rank_emoji} â€”  <b>{title}</b> ã€Œ{catë5 â­ {score}"]
    if summary:
        lines.append(f"ğŸ“ {summary}")
    if why:
        lines.append(f"ğŸ’¡ {why}")

    link_parts = [f'<a href="{url}">ğŸ”— Link</a>']
    if ext_url and ext_url != url:
        link_parts.append(f's<a href="{ext_url}">ğŸ¯ Demo</a>')
    if item.get("is_open_source"):
        link_parts.append("ğŸ“‚ OSS")
    link_parts.append(f"ğŸ‘¤ {builder.title()}")
    lines.append(" | ".join(link_parts))

    if velocity_flag:
        vel = round(item.get("velocity", 0), 1)
        lines.append(f"ğŸš  <b>Velocity:</b> {vel}/hr")

    return "\n".join(lines)


def _format_digest_footer(
    pipeline_stats: dict,
    category_counts: dict,
    velocity_alerts: int,
    taste_accuracy: float | None,
    items: list[dict],
) -> str:
    """Format the footer stats message for the digest."""
    lines = ["â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”", "", "8'ã“Š <b>Today's Category Map:</b>"]

    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        bar = "â–ˆ" * min(count, 5) + "â–‘" * max(0, 5 - count)
        emoji = CAT_EMOJI.get(cat, "ğŸ“¦")
        lines.append(f"{emoji} {cat}: {bar} {count}")

    if velocity_alerts > 0:
        lines.append(f"\nğŸš€ <b>Velocity Alerts:</b> {velocity_alerts} posts blowing up")

    scanned = pipeline_stats.get("total_scanned", 0)
    filtered = pipeline_stats.get("pre_filtered", 0)
    scored = pipeline_stats.get("llm_scored", 0)
    delivered = pipeline_stats.get("delivered", 0)
    sources_ok = pipeline_stats.get("sources_active", 0)
    sources_total = pipeline_stats.get("sources_total", 0)
    source_errors = pipeline_stats.get("source_errors", [])

    lines.append("")
    lines.append("â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”")
    lines.append(f"âš™ï¸ {scanned:,} scanned â†’ {filtered} filtered â†’ {scored} scored â†’ {delivered} delivered")

    source_status = f"ğŸ“¡ Sources: {sources_ok}/{sources_total} âœ…"
    if source_errors:
        source_status += " | " + " | ".join(f"°ƒŠv0ˆ™½ÈÌ¥¸Í½ÕÉ•}•ÉÉ½ÉÌ¤(€€€±¥¹•Ì¹…ÁÁ•¹¡Í½ÕÉ•}ÍÑ…ÑÕÌ¤((€€€¥˜Ñ…ÍÑ•}…ÕÉ…ä¥Ì¹½Ğ9½¹”è(€€€€€€€±¥¹•Ì¹…ÁÁ•¹¡˜‹Â~:¼Q…ÍÑ”5…Ñ èíÑ…ÍÑ•}…ÕÉ…äè¸À•ôˆ¤((€€€¥˜…¹ä¡¥Ñ•´¹•Ğ ‰}™…±±‰…¬ˆ¤™½È¥Ñ•´¥¸¥Ñ•µÌ¤è(€€€€€€€±¥¹•Ì¹…ÁÁ•¹ ‰q»Šjƒ¾â<€ñ¤ù$Í½É¥¹œÕ¹…Ù…¥±…‰±”ƒŠPÉ…¹­•‰ä•¹…•µ•¹Ğğ½¤øˆ¤((€€€±¥¹•Ì¹…ÁÁ•¹ ‹ŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRŠRˆ¤(€€€É•ÑÕÉ¸€‰q¸ˆ¹©½¥¸¡±¥¹•Ì¤(()‘•˜}‰Õ¥±‘}¥Ñ•µ}™••‘‰…­}­•å‰½…É¡¥Ñ•µ}¥èÍÑÈ¤€´ø‘¥Ğğ9½¹”è(€€€ˆˆ‰	Õ¥±¥¹±¥¹”­•å‰½…Éİ¥Ñ ƒÂ~F4¿Â~F8™½È„Í¥¹±”¥Ñ•´¸ˆˆˆ(€€€¥˜¹½Ğ1%YIe}¹•Ğ ‰Ñ•±•É…´ˆ°íô¤¹•Ğ ‰™••‘‰…­}‰ÕÑÑ½¹Ìˆ°QÉÕ”¤è(€€€€€€€É•ÑÕÉ¸9½¹”((€€€€Œ…±±‰…¬‘…Ñ„µ…à°ØĞ‰åÑ•ÌƒŠPÕÍ”Í¡½ÉĞÁÉ•™¥à€¬ÑÉÕ¹…Ñ•¥Ñ•µ}¥(€€€É•ÑÕÉ¸ì(€€€€€€€€‰¥¹±¥¹•}­•å‰½…Éˆèl(€€€€€€€€€€€l(€€€€€€€€€€€€€€€ì‰Ñ•áĞˆè€‹Â~F4ˆ°€‰…±±‰…­}‘…Ñ„ˆè›Šr1}í¥Ñ•µ}¥‘lèÄÙuô‰ô°(€€€€€€€€€€€€€€€ì‰Ñ•áĞˆè€‹Â~F;Š°€‰…±±‰…­}‘…Ñ„ˆè˜‹Šr5}í¥Ñ•µ}¥‘lèÄÙuô‰ô°(€€€€€€€€€€€t(€€€€€€€t(€€€ô(()…Íå¹Œ‘•˜}Í•¹‘}İ¥Ñ¡}­•å‰½…É¡Ñ•áĞèÍÑÈ°­•å‰½…Éè‘¥Ğğ9½¹”€ô9½¹”¤è(€€€ˆˆ‰M•¹„Í¥¹±”µ•ÍÍ…”İ¥Ñ ½ÁÑ¥½¹…°¥¹±¥¹”­•å‰½…É¸ˆˆˆ(€€€¥˜¹½ĞQ1I5}	=Q}Q=-8½È¹½ĞQ1I5}!Q}%è(€€€€€€€¥µÁ½ÉĞÉ”(€€€€€€€ÁÉ¥¹Ğ¡É”¹ÍÕˆ¡Èˆñmxùt¬øˆ°€ˆˆ°Ñ•áĞ¤¤(€€€€€€€ÁÉ¥¹Ğ ˆ´´´ˆ¤(€€€€€€€É•ÑÕÉ¸((€€€…Á¥}ÕÉ°€ô˜‰¡ÑÑÁÌè¼½…Á¤¹Ñ•±•É…´¹½Éœ½‰½ÑíQ1I5}	=Q}Q=-9ô½Í•¹‘5•ÍÍ…”ˆ(€€€Á…ÉÍ•}µ½‘”€ô1%YIe}¹•Ğ ‰Ñ•±•É…´ˆ°íô¤¹•Ğ ‰Á…ÉÍ•}µ½‘”ˆ°€‰!Q50ˆ¤((€€€Á…å±½…€ôì(€€€€€€€€‰¡…Ñ}¥ˆèQ1I5}!Q}%°(€€€€€€€€‰Ñ•áĞˆèÑ•áĞ°(€€€€€€€€‰Á…ÉÍ•}µ½‘”ˆèÁ…ÉÍ•}µ½‘”°(€€€€€€€€‰‘¥Í…‰±•}İ•‰}Á…•}ÁÉ•Ù¥•Üˆè1%YIe}¹•Ğ ‰Ñ•±•É…´ˆ°íô¤¹•Ğ ‰‘¥Í…‰±•}ÁÉ•Ù¥•Üˆ°QÉÕ”¤°(€€€ô(€€€¥˜­•å‰½…Éè(€€€€€€€Á…å±½…‘l‰É•Á±å}µ…É­ÕÀ‰t€ô©Í½¸¹‘ÕµÁÌ¡­•å‰½…É¤((€€€…Íå¹Œİ¥Ñ ¡ÑÑÁà¹Íå¹±¥•¹Ğ ¤…Ì±¥•¹Ğè(€€€€€€€ÑÉäè(€€€€€€€€€€€É•ÍÀ€ô…İ…¥Ğ±¥•¹Ğ¹Á½ÍĞ¡…Á¥}ÕÉ°°©Í½¸õÁ…å±½…°Ñ¥µ•½ÕĞôÌÀ¤(€€€€€€€€€€€É•ÍÀ¹É…¥Í•}™½É}ÍÑ…ÑÕÌ ¤(€€€€€€€•á•ÁĞá•ÁÑ¥½¸…Ì”è(€€€€€€€€€€€±½œ¹•ÉÉ½È ‰¥Ñ•µ}Í•¹‘}™…¥±•ˆ°•ÉÉ½ÈõÍÑÈ¡”¤¤(()‘•˜}‰Õ¥±‘}™••‘‰…­}­•å‰½…É¡¥Ñ•µ}¥‘Ìè±¥ÍÑmÍÑÉt¤€´ø‘¥Ğğ9½¹”è(€€€€ˆˆ‰	Õ¥±…É•…Ñ”™••‘‰…¬­•å‰½…É€¡­•ÁĞ™½È…±•ÉÑÌ½É•Á½ÉÑÌ¤¸ˆˆˆ(€€€¥˜¹½Ğ1%YIe}¹•Ğ ‰Ñ•±•É…´ˆ°íô¤¹•Ğ ‰™••‘‰…­}‰ÕÑÑ½¹Ìˆ°QÉÕ”¤è(€€€€€€€É•ÑÕÉ¸9½¹”((€€€É•ÑÕÉ¸ì(€€€€€€€€‰¥¹±¥¹•}­•å‰½…Éˆèl(€€€€€€€€€€€l(€€€€€€€€€€€€€€€ì‰Ñ•áĞˆè€‹Â~F4É•…Ğ„ˆ°€‰…±±‰…­}‘…Ñ„ˆè˜‰ÕÁ}í¥Ñ•µ}¥‘ÍlÁulèÄÙuô‰ô°(€€€€€€€€€€€€€€€ì‰Ñ•áĞˆè€‹Â~F89½ĞÕÍ•™Õ°ˆ°€‰…±±‰…­}‘…Ñ„ˆè˜‹Šr5}í¥Ñ•µ}¥‘ÍlÁulèÄÙuô‰ô°(€€€€€€€€€€€t(€€€€€€€t(€€€ô(()‘•˜}ÍÁ±¥Ñ}µ•ÍÍ…”¡Ñ•áĞèÍÑÈ°µ…á}±•¸è¥¹Ğ€ô€ĞÀÀÀ¤€´ø±¥ÍÑmÍÑÉtè(€€€ˆˆ‰MÁ±¥Ğ„±½¹œµ•ÍÍ…”¥¹Ñ¼Q•±•É…´µÍ…™”¡Õ¹­Ì¸ˆˆˆ(€€€¥˜±•¸¡Ñ•áĞ¤€ğôµ…á}±•¸è(€€€€€€€É•ÑÕÉ¸mÑ•áÑt((€€€¡Õ¹­Ì€ômt(€€€ÕÉÉ•¹Ğ€ô€ˆˆ(€€€™½È±¥¹”¥¸Ñ•áĞ¹ÍÁ±¥Ğ ‰q¸ˆ¤è(€€€€€€€¥˜±•¸¡ÕÉÉ•¹Ğ¤€¬±•¸¡±¥¹”¤€¬€Ä€øµ…á}±•¸è(€€€€€€€€€€€¥˜ÕÉÉ•¹Ğè(€€€€€€€€€€€€€€€¡Õ¹­Ì¹…ÁÁ•¹¡ÕÉÉ•¹Ğ¤(€€€€€€€€€€€ÕÉÉ•¹Ğ€ô±¥¹”(€€€€€€€•±Í”è(€€€€€€€€€€€ÕÉÉ•¹Ğ€ô˜‰íÕÉÉ•¹Ñõq¹í±¥¹•ôˆ¥˜ÕÉÉ•¹Ğ•±Í”±¥¹”((€€€¥˜ÕÉÉ•¹Ğè(€€€€€€€¡Õ¹­Ì¹…ÁÁ•¹¡ÕÉÉ•¹Ğ¤((€€€É•ÑÕÉ¸¡Õ¹­Ì(()‘•˜}•Í…Á•}¡Ñµ°¡Ñ•áĞèÍÑÈ¤€´øÍÑÈè(€€€€ˆˆ‰Í…Á”!Q50ÍÁ•¥…°¡…É…Ñ•ÉÌ™½ÈQ•±•É…´!Q50Á…ÉÍ”µ½‘”¸ˆˆˆ(€€€É•ÑÕÉ¸€ (€€€€€€€Ñ•áĞ¹É•Á±…” ˆ˜ˆ°€ˆ™…µÀìˆ¤(€€€€€€€€¹É•Á±…” ˆğˆ°€ˆ™±Ğìˆ¤(€€€€€€€€¹É•Á±…” ˆøˆ°€ˆ™Ğìˆ¤(€€€€¤(