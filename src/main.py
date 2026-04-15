"""
Main orchestrator — coordinates the entire pipeline from fetch to delivery.

Usage:
    python -m src.main                          # Full daily digest run
    python -m src.main --dry-run                # Run without sending to Telegram
    python -m src.main --source reddit          # Test a single source
    python -m src.main --mode alert             # Real-time alert check only
    python -m src.main --mode weekly            # Generate weekly report
    python -m src.main --mode monthly           # Generate monthly report
    python -m src.main --mode feedback          # Run feedback bot (long-polling)
    python -m src.main --debug                  # Verbose logging
"""

import asyncio
import argparse
import sys
from datetime import datetime, timezone

from src.config import DRY_RUN, MAX_DAILY_ITEMS, SOURCES_CFG
from src.sources import ALL_SOURCES, SourceItem
from src.pipeline.pre_filter import pre_filter
from src.pipeline.velocity import calculate_velocity_flags, get_velocity_alerts
from src.pipeline.scorer import score_items
from src.pipeline.dedup import deduplicate, cluster_by_category
from src.pipeline.taste_model import apply_taste_adjustments
from src.delivery.telegram import send_daily_digest
from src.delivery.alerts import check_and_send_alerts
from src.delivery.weekly_report import generate_and_send_weekly_report
from src.delivery.monthly_report import generate_and_send_monthly_report
from src.persistence.daily_log import save_daily_log, load_recent_urls
from src.persistence.knowledge_graph import update_knowledge_graph
from src.persistence.stats import PipelineStats
from src.persistence.source_health import record_source_results, get_sources_needing_alert, format_health_footer
from src.feedback.handler import get_taste_accuracy, run_feedback_bot
from src.utils.http_client import close_client
from src.utils.logger import setup_logging, get_logger


log = get_logger("main")


async def run_daily_digest(source_filter: str | None = None, dry_run: bool = False):
    """
    Full daily digest pipeline:
    1. Fetch from all sources (parallel)
    2. Pre-filter (rule-based)
    3. Velocity detection
    4. LLM scoring (Claude Sonnet)
    5. Dedup + taste adjustment
    6. Deliver to Telegram
    7. Persist logs + knowledge graph
    """
    stats = PipelineStats()
    start_time = datetime.now(timezone.utc)

    log.info("pipeline_start", mode="daily_digest", source_filter=source_filter, dry_run=dry_run)

    # ── Step 1: Fetch from sources ──────────────────────────
    all_items: list[SourceItem] = []
    sources_to_run = {}

    for name, source_cls in ALL_SOURCES.items():
        if source_filter and name != source_filter:
            continue
        if source_cls().is_enabled(SOURCES_CFG):
            sources_to_run[name] = source_cls()

    stats.sources_total = len(sources_to_run)

    # Parallel fetch
    fetch_tasks = {name: src.fetch() for name, src in sources_to_run.items()}
    results = {}

    for name, task in fetch_tasks.items():
        try:
            items = await task
            results[name] = items
            stats.source_counts[name] = len(items)
            stats.sources_active += 1
            log.info("source_complete", source=name, items=len(items))
        except Exception as e:
            log.error("source_failed", source=name, error=str(e))
            stats.source_errors.append(name)
            results[name] = []

    for items in results.values():
        all_items.extend(items)

    stats.total_scanned = len(all_items)
    log.info("fetch_complete", total_items=len(all_items), sources_ok=stats.sources_active)

    if not all_items:
        log.warning("no_items_fetched")
        if not dry_run:
            # Send a "system down" alert if all sources failed
            from src.delivery.telegram import send_telegram_message
            await send_telegram_message("⚠️ <b>AI Intelligence System:</b> No items fetched today. All sources may be down.")
        return

    # ── Step 2: Pre-filter ──────────────────────────────────
    seen_urls = load_recent_urls(days=7)
    filtered_items = pre_filter(all_items, seen_urls)
    stats.pre_filtered = len(filtered_items)
    log.info("pre_filter_complete", passed=len(filtered_items))

    # ── Step 3: Velocity detection ──────────────────────────
    filtered_items = calculate_velocity_flags(filtered_items)
    velocity_alerts = get_velocity_alerts(filtered_items)
    log.info("velocity_complete", alerts=len(velocity_alerts))

    # ── Step 4: LLM scoring ────────────────────────────────
    scored_items = await score_items(filtered_items)
    stats.llm_scored = len(scored_items)
    log.info("scoring_complete", scored=len(scored_items))

    # ── Step 5: Dedup + taste adjustment ────────────────────
    deduped = deduplicate(scored_items)
    adjusted = apply_taste_adjustments(deduped)

    # Final selection — top N items
    final_items = adjusted[:MAX_DAILY_ITEMS]
    stats.delivered = len(final_items)

    # Category breakdown
    category_counts = {}
    for item in adjusted:
        cat = item.get("category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # ── Step 6: Deliver ────────────────────────────────────
    taste_accuracy = get_taste_accuracy()

    if dry_run:
        log.info("dry_run_mode", msg="Skipping Telegram send")
        # Still format the message for display
        from src.delivery.telegram import format_daily_digest
        message = format_daily_digest(
            final_items, stats.to_dict(), category_counts,
            len(velocity_alerts), taste_accuracy,
        )
        import re
        print("\n" + "=" * 60)
        print("DRY RUN — DAILY DIGEST:")
        print("=" * 60)
        print(re.sub(r"<[^>]+>", "", message))
        print("=" * 60 + "\n")
    else:
        await send_daily_digest(
            final_items, stats.to_dict(), category_counts,
            len(velocity_alerts), taste_accuracy,
        )

    # ── Step 7: Persist ─────────────────────────────────────
    save_daily_log(adjusted, stats.to_dict(), category_counts, len(velocity_alerts))
    update_knowledge_graph(adjusted, category_counts)

    # ── Step 8: Source health tracking ──────────────────────
    record_source_results(stats.source_counts, stats.source_errors)

    # Check for sources failing 3+ consecutive days
    sick_sources = get_sources_needing_alert(threshold_days=3)
    if sick_sources and not dry_run:
        from src.delivery.telegram import send_telegram_message
        alert_lines = ["⚠️ <b>Source Health Alert:</b>", ""]
        for s in sick_sources:
            alert_lines.append(
                f"❌ <b>{s['source']}</b> — failed {s['consecutive_failures']} consecutive days "
                f"(last success: {s['last_success']})"
            )
        alert_lines.append("\nCheck API keys, rate limits, or source availability.")
        await send_telegram_message("\n".join(alert_lines))
        log.warning("source_health_alert", sources=[s["source"] for s in sick_sources])

    # ── Step 9: Check for breakthrough alerts ───────────────
    if not dry_run:
        await check_and_send_alerts(scored_items)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    log.info(
        "pipeline_complete",
        elapsed_seconds=round(elapsed, 1),
        scanned=stats.total_scanned,
        delivered=stats.delivered,
    )


async def run_alert_check():
    """Lightweight check for breakthrough items (runs every 4 hours)."""
    log.info("alert_check_start")

    # Only fetch from fast sources
    fast_sources = ["reddit", "hackernews"]
    all_items: list[SourceItem] = []

    for name in fast_sources:
        if name in ALL_SOURCES and ALL_SOURCES[name]().is_enabled(SOURCES_CFG):
            try:
                items = await ALL_SOURCES[name]().fetch()
                all_items.extend(items)
            except Exception as e:
                log.warning("alert_source_failed", source=name, error=str(e))

    if not all_items:
        log.info("no_items_for_alert_check")
        return

    filtered = pre_filter(all_items)
    filtered = calculate_velocity_flags(filtered)

    # Only score velocity flagged items to save API cost
    hot_items = [i for i in filtered if getattr(i, "_velocity_flag", False)]
    if hot_items:
        scored = await score_items(hot_items)
        await check_and_send_alerts(scored)

    log.info("alert_check_complete")


async def main():
    parser = argparse.ArgumentParser(description="AI Intelligence Digest System")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending to Telegram")
    parser.add_argument("--source", type=str, help="Test a single source (e.g., reddit, hackernews)")
    parser.add_argument("--mode", type=str, default="daily",
                        choices=["daily", "alert", "weekly", "monthly", "feedback", "taste-update"],
                        help="Run mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()
    setup_logging(debug=args.debug)

    dry_run = args.dry_run or DRY_RUN

    try:
        if args.mode == "daily":
            await run_daily_digest(source_filter=args.source, dry_run=dry_run)
        elif args.mode == "alert":
            await run_alert_check()
        elif args.mode == "weekly":
            await generate_and_send_weekly_report()
        elif args.mode == "monthly":
            await generate_and_send_monthly_report()
        elif args.mode == "feedback":
            await run_feedback_bot()
        elif args.mode == "taste-update":
            from src.feedback.taste_updater import recalculate_full_profile
            recalculate_full_profile()
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
