"""
Main orchestrator for AI Daily Digest pipeline.
Runs the complete workflow: fetch, filter, score, deduplicate, deliver.

Architecture note: Sources return plain dicts. Some pipeline modules
(velocity, scorer) expect SourceItem dataclass objects. This orchestrator
uses inline heuristic scoring that works with dicts directly, falling back
to LLM scoring only when GROQ_API_KEY is available.
"""

import asyncio
import argparse
import sys
import logging
import re
from datetime import datetime, timezone
from collections import Counter

from src.config import (
    DRY_RUN, MAX_DAILY_ITEMS, SOURCES_CFG, GROQ_API_KEY,
)
from src.sources import ALL_SOURCES
from src.pipeline.pre_filter import pre_filter
from src.pipeline.dedup import deduplicate
from src.pipeline.taste_model import apply_taste_adjustments
from src.delivery.telegram import send_daily_digest
from src.persistence.daily_log import save_daily_log, load_recent_urls
from src.persistence.source_health import record_source_results

log = logging.getLogger("daily_digest")

# ---------------------------------------------------------------------------
# Heuristic scoring (works with plain dicts -- no SourceItem needed)
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS = {
    "AI/ML": r"(?i)\b(ai|ml|llm|gpt|claude|gemini|transformer|neural|diffusion|deep.?learn|machine.?learn|openai|anthropic|mistral|llama|fine.?tun|embed|rag|vector|token|prompt|bert|vision.?model)\b",
    "Dev Tools": r"(?i)\b(github|vscode|docker|kubernetes|k8s|terraform|ci/cd|devops|git|api|sdk|cli|framework|library|package|npm|pip|rust|golang|typescript)\b",
    "Product Launch": r"(?i)\b(launch|ship|release|announce|introduce|unveil|beta|alpha|v\d|waitlist|generally.?available|ga\b|open.?source)\b",
    "Funding": r"(?i)\b(rais|fund|seed|series.[a-d]|valuation|invest|vc|venture|unicorn|ipo|acqui)\b",
    "Research": r"(?i)\b(paper|arxiv|research|study|benchmark|ablation|sota|state.of.the.art|peer.review|experiment|findings|dataset)\b",
    "Cloud/Infra": r"(?i)\b(aws|azure|gcp|cloud|serverless|lambda|s3|database|postgres|redis|kafka|microservice|cdn|edge)\b",
    "Crypto/Web3": r"(?i)\b(crypto|bitcoin|ethereum|blockchain|web3|nft|defi|dao|token|solana|wallet)\b",
    "Security": r"(?i)\b(security|vulnerab|exploit|breach|cve|patch|zero.?day|malware|ransomware|auth|encrypt)\b",
}


def _guess_category(item: dict) -> str:
    """Guess item category from title + summary text."""
    text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('description', '')}"
    scores = {}
    for cat, pattern in _CATEGORY_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            scores[cat] = len(matches)
    if scores:
        return max(scores, key=scores.get)
    return "General"


def _heuristic_score(item: dict) -> float:
    """Score an item 0-10 using engagement signals and freshness."""
    score = 5.0  # baseline

    # Engagement boost
    eng = item.get("engagement", {})
    if isinstance(eng, dict):
        points = eng.get("points", 0) or eng.get("upvotes", 0) or eng.get("stars", 0) or 0
        comments = eng.get("comments", 0) or eng.get("num_comments", 0) or 0
    else:
        points = 0
        comments = 0

    if points > 500:
        score += 2.0
    elif points > 100:
        score += 1.5
    elif points > 30:
        score += 0.8

    if comments > 100:
        score += 1.5
    elif comments > 30:
        score += 0.8
    elif comments > 10:
        score += 0.3

    # Source quality bonus
    source = item.get("source", "")
    high_quality_sources = {"arxiv", "github_trending", "producthunt"}
    if source in high_quality_sources:
        score += 0.5

    # Freshness (prefer newer)
    date_str = item.get("date", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if age_hours < 6:
                score += 1.0
            elif age_hours < 12:
                score += 0.5
        except (ValueError, AttributeError):
            pass

    # AI/ML topic bonus (this is an AI digest after all)
    cat = _guess_category(item)
    if cat == "AI/ML":
        score += 1.0
    elif cat == "Research":
        score += 0.5

    return min(round(score, 2), 10.0)


# ---------------------------------------------------------------------------
# Source instantiation
# ---------------------------------------------------------------------------

def _instantiate_sources(source_filter=None):
    """ALL_SOURCES is a dict of {name: SourceClass}. Instantiate them."""
    instances = {}
    for name, cls in ALL_SOURCES.items():
        if source_filter and name != source_filter:
            continue
        src_cfg = SOURCES_CFG.get(name, {})
        if not src_cfg.get("enabled", True):
            log.info(f"Skipping disabled source: {name}")
            continue
        try:
            instances[name] = cls()
        except Exception as e:
            log.warning(f"Failed to instantiate source {name}: {e}")
    return instances


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

async def _fetch_all(sources: dict) -> list[dict]:
    """Fetch items from all sources, return flat list of dicts."""
    all_items = []
    source_counts = {}
    source_errors = []

    for name, src in sources.items():
        try:
            log.info(f"Fetching from {name}...")
            items = await src.fetch()
            # Ensure items are dicts
            parsed = []
            for item in items:
                if isinstance(item, dict):
                    parsed.append(item)
                elif hasattr(item, "__dict__"):
                    parsed.append(vars(item))
                else:
                    parsed.append({"title": str(item), "source": name})
            # Tag source if missing
            for item in parsed:
                if "source" not in item:
                    item["source"] = name
            source_counts[name] = len(parsed)
            all_items.extend(parsed)
            log.info(f"  {name}: {len(parsed)} items")
        except Exception as e:
            log.error(f"  {name} FAILED: {e}")
            source_counts[name] = 0
            source_errors.append(f"{name}: {e}")

    # Record health
    try:
        record_source_results(source_counts, source_errors)
    except Exception as e:
        log.warning(f"Failed to record source health: {e}")

    return all_items


def _score_items(items: list[dict]) -> list[dict]:
    """Apply heuristic scoring to all items."""
    for item in items:
        item["score"] = _heuristic_score(item)
        item["final_score"] = item["score"]
        if "category" not in item:
            item["category"] = _guess_category(item)
    return items


async def run_daily_pipeline(dry_run=False, source_filter=None):
    """Full daily pipeline: fetch → filter → score → dedup → taste → deliver."""
    log.info("=" * 60)
    log.info("Starting AI Daily Digest pipeline")
    log.info(f"  dry_run={dry_run}, source_filter={source_filter}")
    log.info("=" * 60)

    pipeline_stats = {
        "start_time": datetime.now(timezone.utc).isoformat(),
        "sources_fetched": 0,
        "raw_items": 0,
        "after_filter": 0,
        "after_score": 0,
        "after_dedup": 0,
        "final_digest": 0,
    }

    # 1. Fetch
    sources = _instantiate_sources(source_filter)
    pipeline_stats["sources_fetched"] = len(sources)
    log.info(f"Instantiated {len(sources)} sources")

    all_items = await _fetch_all(sources)
    pipeline_stats["raw_items"] = len(all_items)
    log.info(f"Total raw items: {len(all_items)}")

    if not all_items:
        log.warning("No items fetched from any source. Aborting.")
        return

    # 2. Pre-filter
    try:
        recent_urls = load_recent_urls()
    except Exception as e:
        log.warning(f"Failed to load recent URLs: {e}")
        recent_urls = set()

    try:
        filtered = pre_filter(all_items, recent_urls)
    except Exception as e:
        log.error(f"Pre-filter failed: {e}. Using raw items.")
        filtered = all_items
    pipeline_stats["after_filter"] = len(filtered)
    log.info(f"After pre-filter: {len(filtered)} items")

    # 3. Score (heuristic -- no LLM/SourceItem dependency)
    try:
        scored = _score_items(filtered)
    except Exception as e:
        log.error(f"Scoring failed: {e}. Using unscored items.")
        scored = filtered
        for item in scored:
            item.setdefault("score", 5.0)
            item.setdefault("final_score", 5.0)
            item.setdefault("category", "General")
    pipeline_stats["after_score"] = len(scored)
    log.info(f"Scored {len(scored)} items")

    # 4. Deduplicate
    try:
        deduped = deduplicate(scored)
    except Exception as e:
        log.error(f"Dedup failed: {e}. Using scored items.")
        deduped = scored
    pipeline_stats["after_dedup"] = len(deduped)
    log.info(f"After dedup: {len(deduped)} items")

    # 5. Apply taste adjustments
    try:
        adjusted = apply_taste_adjustments(deduped)
    except Exception as e:
        log.error(f"Taste adjustment failed: {e}. Using deduped items.")
        adjusted = deduped
    log.info(f"After taste: {len(adjusted)} items")

    # 6. Sort by score descending + cap
    adjusted.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    final_items = adjusted[:MAX_DAILY_ITEMS]
    pipeline_stats["final_digest"] = len(final_items)
    log.info(f"Final digest: {len(final_items)} items")

    # 7. Compute category breakdown
    category_counts = dict(Counter(item.get("category", "General") for item in final_items))
    log.info(f"Categories: {category_counts}")

    # 8. Save daily log
    try:
        save_daily_log(final_items)
    except Exception as e:
        log.warning(f"Failed to save daily log: {e}")

    # 9. Deliver via Telegram
    if dry_run:
        log.info("[DRY RUN] Skipping Telegram delivery")
        for i, item in enumerate(final_items[:5], 1):
            log.info(f"  #{i}: [{item.get('score', '?')}] {item.get('title', 'untitled')[:80]}")
    else:
        try:
            await send_daily_digest(
                final_items,
                pipeline_stats=pipeline_stats,
                category_counts=category_counts,
            )
            log.info("Telegram delivery complete!")
        except Exception as e:
            log.error(f"Telegram delivery failed: {e}", exc_info=True)

    pipeline_stats["end_time"] = datetime.now(timezone.utc).isoformat()
    log.info("Pipeline finished successfully.")
    log.info(f"Stats: {pipeline_stats}")
    return pipeline_stats


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Daily Digest -- fetch, score, and deliver top items"
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "alert", "weekly", "monthly", "feedback"],
        default="daily",
        help="Pipeline mode to run (default: daily)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run -- do not send to Telegram",
    )
    parser.add_argument(
        "--source",
        type=str,
        help="Filter to specific source name (e.g., --source twitter)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main():
    """Parse args and run the appropriate pipeline mode."""
    args = parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    dry_run = args.dry_run or DRY_RUN

    if args.mode == "daily":
        asyncio.run(run_daily_pipeline(dry_run=dry_run, source_filter=args.source))
    elif args.mode == "alert":
        log.info("Alert mode -- not yet fully implemented with dict pipeline")
    elif args.mode == "weekly":
        log.info("Weekly report mode -- not yet fully implemented with dict pipeline")
    elif args.mode == "monthly":
        log.info("Monthly report mode -- not yet fully implemented with dict pipeline")
    elif args.mode == "feedback":
        log.info("Feedback mode -- not yet fully implemented with dict pipeline")
    else:
        log.error(f"Unknown mode: {args.mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
