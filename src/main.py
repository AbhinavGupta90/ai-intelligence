"""
Main orchestrator for AI Daily Digest pipeline.
Runs the complete workflow: fetch, filter, score, deduplicate, deliver.
"""

import asyncio
import argparse
import sys
import logging
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
from src.persistence.source_health import record_source_results
from src.utils.logger import get_logger

log = get_logger("main")


def _instantiate_sources(source_filter=None):
    """Instantiate source classes from ALL_SOURCES registry dict."""
    sources = []
    for name, source_cls in ALL_SOURCES.items():
        if source_filter and name != source_filter:
            continue
        try:
            instance = source_cls()
            sources.append((name, instance))
        except Exception as e:
            log.error(f"Failed to instantiate source {name}: {e}")
    return sources


async def run_daily_digest(source_filter=None, dry_run=False):
    """
    Main daily digest pipeline.
    """
    stats = PipelineStats()
    source_counts = {}
    source_errors = []

    try:
        log.info("Starting daily digest pipeline")

        # Fetch from all sources
        all_items = []
        for name, source in _instantiate_sources(source_filter):
            try:
                log.info(f"Fetching from {name}")
                items = await source.fetch()
                all_items.extend(items)
                source_counts[name] = len(items)
            except Exception as e:
                log.error(f"Failed to fetch from {name}: {e}")
                source_errors.append(name)

        # Record source health (aggregated)
        record_source_results(source_counts, source_errors)

        stats.raw_items = len(all_items)
        log.info(f"Fetched {stats.raw_items} items total")

        # Pre-filter
        filtered_items = pre_filter(all_items, load_recent_urls())
        stats.after_prefilter = len(filtered_items)
        log.info(f"After pre-filter: {stats.after_prefilter} items")

        # Calculate velocity flags
        for item in filtered_items:
            item["velocity_flags"] = calculate_velocity_flags(item)

        # Score items
        scored_items = score_items(filtered_items)
        log.info(f"Scored {len(scored_items)} items")

        # Deduplicate
        deduped = deduplicate(scored_items)
        stats.after_dedup = len(deduped)
        log.info(f"After dedup: {stats.after_dedup} items")

        # Cluster by category
        clustered = cluster_by_category(deduped)
        log.info(f"Clustered into {len(clustered)} categories")

        # Apply taste adjustments
        taste_adjusted = apply_taste_adjustments(clustered)
        log.info(f"Applied taste adjustments to {len(taste_adjusted)} items")

        # Sort by score descending
        taste_adjusted.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        # Cap at MAX_DAILY_ITEMS
        final_items = taste_adjusted[:MAX_DAILY_ITEMS]
        stats.final_digest = len(final_items)
        log.info(f"Final digest: {stats.final_digest} items (capped at {MAX_DAILY_ITEMS})")

        # Send via Telegram
        if not dry_run and final_items:
            await send_daily_digest(final_items)
            log.info("Sent daily digest via Telegram")

        # Save daily log
        save_daily_log(final_items, stats)
        log.info("Saved daily log")

        # Update knowledge graph
        update_knowledge_graph(final_items)
        log.info("Updated knowledge graph")

        log.info(f"Daily digest complete. Stats: {stats}")
        return final_items

    except Exception as e:
        log.error(f"Daily digest pipeline failed: {e}", exc_info=True)
        raise


async def run_alert_check():
    """
    Check for high-velocity items and send alerts.
    """
    try:
        log.info("Starting alert check")

        all_items = []
        for name, source in _instantiate_sources():
            try:
                items = await source.fetch()
                all_items.extend(items)
            except Exception as e:
                log.error(f"Failed to fetch from {name}: {e}")

        log.info(f"Fetched {len(all_items)} items for alert check")

        # Calculate velocity flags
        for item in all_items:
            item["velocity_flags"] = calculate_velocity_flags(item)

        # Get high-velocity alerts
        alerts = get_velocity_alerts(all_items)
        if alerts:
            log.info(f"Found {len(alerts)} high-velocity items, sending alerts")
            await check_and_send_alerts(alerts)
        else:
            log.info("No high-velocity items to alert on")

    except Exception as e:
        log.error(f"Alert check failed: {e}", exc_info=True)
        raise


async def run_weekly():
    """Generate and send weekly report."""
    try:
        log.info("Starting weekly report generation")
        await generate_and_send_weekly_report()
        log.info("Weekly report sent")
    except Exception as e:
        log.error(f"Weekly report failed: {e}", exc_info=True)
        raise


async def run_monthly():
    """Generate and send monthly report."""
    try:
        log.info("Starting monthly report generation")
        await generate_and_send_monthly_report()
        log.info("Monthly report sent")
    except Exception as e:
        log.error(f"Monthly report failed: {e}", exc_info=True)
        raise


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Daily Digest -- fetch, score, and deliver top items"
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "alert", "weekly", "monthly", "feedback"],
        default="daily",
        help="Pipeline mode to run (default: daily)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run -- do not send to Telegram"
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Filter to specific source name (e.g., --source twitter)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    return parser.parse_args()


def main():
    """Parse args, configure logging, and run the appropriate pipeline."""
    args = parse_args()

    # Configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    log.info(f"Starting AI Daily Digest -- mode={args.mode}, dry_run={args.dry_run}")

    # Route to appropriate handler
    if args.mode == "daily":
        asyncio.run(run_daily_digest(
            source_filter=args.source,
            dry_run=args.dry_run or DRY_RUN
        ))
    elif args.mode == "alert":
        asyncio.run(run_alert_check())
    elif args.mode == "weekly":
        asyncio.run(run_weekly())
    elif args.mode == "monthly":
        asyncio.run(run_monthly())
    else:
        log.error(f"Unknown mode: {args.mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
