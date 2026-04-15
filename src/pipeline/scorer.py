"""
LLM Scorer — sends batched items to an LLM for intelligent scoring.

Backend priority:
  1. Groq Llama 3.3 70B (FREE — default, 30 RPM / 1000 RPD)
  2. Anthropic Claude Sonnet (paid — opt-in via ANTHROPIC_API_KEY)
  3. Fallback heuristic (engagement-based, no API needed)

Set GROQ_API_KEY for free scoring. Get one at https://console.groq.com/keys
"""

import json
import asyncio
from src.sources.base import SourceItem
from src.config import ANTHROPIC_API_KEY, BATCH_SIZE, BONUSES
from src.utils.logger import get_logger
import os

log = get_logger("pipeline.scorer")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

SCORER_SYSTEM_PROMPT = """You are an elite AI trend analyst working for a senior tech professional.
Your job is to find the most interesting, novel, and impressive things people are BUILDING with AI.

SCORING CRITERIA (weighted):
1. NOVELTY (35%): Is this genuinely new? A new approach, combination, or application?
   Score 1 if it is another ChatGPT wrapper. Score 10 if it is something you have never seen before.

2. TECHNICAL DEPTH (25%): Is there real engineering here?
   A weekend hack scores 4. A well-architected system with novel solutions scores 9.

3. WOW FACTOR (25%): Would a senior engineer say "damn, that is cool"?
   The gut reaction test.

4. PRACTICAL VALUE (15%): Can someone actually use this?
   Theoretical research with no demo = lower score. Working tool you can try = higher.

HARD RULES:
- ONLY score 8+ if someone actually BUILT something tangible
- News articles, opinions, tutorials = automatic 3 or below
- "I asked ChatGPT to..." posts = automatic 2
- Genuine open-source releases from known teams get +1 bonus
- First-time builders shipping something real get +0.5 empathy bonus
- If it has a working demo/video, +0.5 bonus

RESPOND WITH ONLY VALID JSON — no markdown, no commentary. Output a JSON array."""

SCORER_USER_TEMPLATE = """Score these {count} items. For each, return:
{{
  "item_id": "the item_id from input",
  "score": 8.5,
  "novelty": 8,
  "depth": 7,
  "wow": 9,
  "practical": 8,
  "category": "one of: agent, voice_ai, dev_tool, creative_ai, infra, research, local_llm, multimodal, robotics, other",
  "summary": "2-line summary of what was built",
  "why_interesting": "1-line insight on why this matters",
  "builder_type": "one of: startup, indie, bigtech, researcher, hobbyist, unknown"
}}

Items to score:
{items_json}"""


def _get_backend() -> str:
    """Determine which LLM backend to use."""
    if GROQ_API_KEY:
        return "groq"
    if ANTHROPIC_API_KEY:
        return "anthropic"
    return "fallback"


async def score_items(items: list[SourceItem]) -> list[dict]:
    """
    Score a list of pre-filtered items using the best available LLM.
    Returns list of scored item dicts with all scoring metadata.
    """
    if not items:
        return []

    backend = _get_backend()
    log.info("scoring_backend", backend=backend, items=len(items))

    if backend == "fallback":
        log.warning("no_api_key", msg="No GROQ_API_KEY or ANTHROPIC_API_KEY — using heuristic scoring")
        return _fallback_scoring(items)

    all_scored = []

    # Process in batches
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        log.info("scoring_batch", batch_num=i // BATCH_SIZE + 1, size=len(batch))
        try:
            if backend == "groq":
                scored = await _score_batch_groq(batch)
            else:
                scored = await _score_batch_anthropic(batch)
            all_scored.extend(scored)
        except Exception as e:
            log.error("scoring_failed", batch_start=i, error=str(e))
            all_scored.extend(_fallback_scoring(batch))

    # Apply bonuses
    for scored_item in all_scored:
        _apply_bonuses(scored_item)

    # Sort by final score descending
    all_scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    log.info("scoring_complete", total_scored=len(all_scored), backend=backend)
    return all_scored


async def _score_batch_groq(items: list[SourceItem]) -> list[dict]:
    """Score a batch using Groq (FREE — Llama 3.3 70B, blazing fast)."""
    from groq import AsyncGroq

    client = AsyncGroq(api_key=GROQ_API_KEY)
    items_for_prompt = _prepare_items(items)

    user_msg = SCORER_USER_TEMPLATE.format(
        count=len(items_for_prompt),
        items_json=json.dumps(items_for_prompt, indent=2),
    )

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SCORER_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    return _parse_scores(response.choices[0].message.content, items)


async def _score_batch_anthropic(items: list[SourceItem]) -> list[dict]:
    """Score a batch using Anthropic Claude (paid fallback)."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    items_for_prompt = _prepare_items(items)

    user_msg = SCORER_USER_TEMPLATE.format(
        count=len(items_for_prompt),
        items_json=json.dumps(items_for_prompt, indent=2),
    )

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": SCORER_SYSTEM_PROMPT + "\n\n" + user_msg},
        ],
    )

    return _parse_scores(response.content[0].text, items)


def _prepare_items(items: list[SourceItem]) -> list[dict]:
    """Convert SourceItems to dicts for the LLM prompt."""
    return [
        {
            "item_id": item.item_id,
            "title": item.title,
            "source": item.source,
            "url": item.url,
            "engagement": item.engagement or {},
            "summary": (item.summary or "")[:500],
        }
        for item in items
    ]


def _parse_scores(raw_response: str, original_items: list[SourceItem]) -> list[dict]:
    """Parse LLM JSON response into scored item dicts."""
    try:
        data = json.loads(raw_response)
        # Handle both direct array and {"items": [...]} format
        if isinstance(data, dict):
            data = data.get("items", data.get("scores", []))
        if not isinstance(data, list):
            data = [data]
    except json.JSONDecodeError as e:
        log.error("json_parse_failed", error=str(e), response=raw_response[:300])
        return _fallback_scoring(original_items)

    # Build lookup for original items
    item_lookup = {item.item_id: item for item in original_items}
    scored = []

    for entry in data:
        item_id = entry.get("item_id", "")
        original = item_lookup.get(item_id)
        if not original:
            continue

        scored.append({
            "item_id": item_id,
            "title": original.title,
            "url": original.url,
            "source": original.source,
            "score": float(entry.get("score", 5.0)),
            "novelty": entry.get("novelty", 5),
            "depth": entry.get("depth", 5),
            "wow": entry.get("wow", 5),
            "practical": entry.get("practical", 5),
            "category": entry.get("category", "other"),
            "summary": entry.get("summary", original.summary or ""),
            "why_interesting": entry.get("why_interesting", ""),
            "builder_type": entry.get("builder_type", "unknown"),
            "engagement": original.engagement or {},
            "published_at": str(original.published_at) if original.published_at else None,
            "source_score": original.source_score,
        })

    # If some items were missed by LLM, add them with fallback scores
    scored_ids = {s["item_id"] for s in scored}
    for item in original_items:
        if item.item_id not in scored_ids:
            scored.extend(_fallback_scoring([item]))

    return scored


def _fallback_scoring(items: list[SourceItem]) -> list[dict]:
    """Heuristic scoring when no LLM API key is available."""
    scored = []
    for item in items:
        engagement = item.engagement or {}
        points = engagement.get("points", 0) or engagement.get("upvotes", 0) or 0
        comments = engagement.get("comments", 0) or engagement.get("num_comments", 0) or 0

        # Simple heuristic: normalize engagement
        score = min(10.0, 3.0 + (points / 100) + (comments / 50))

        scored.append({
            "item_id": item.item_id,
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "score": round(score, 1),
            "novelty": 5,
            "depth": 5,
            "wow": 5,
            "practical": 5,
            "category": "other",
            "summary": item.summary or "",
            "why_interesting": "Scored via heuristic fallback",
            "builder_type": "unknown",
            "engagement": engagement,
            "published_at": str(item.published_at) if item.published_at else None,
            "source_score": item.source_score,
        })

    return scored


def _apply_bonuses(scored_item: dict) -> None:
    """Apply bonus adjustments based on configured rules."""
    if not BONUSES:
        return

    original_score = scored_item.get("score", 0)
    bonus = 0.0

    if scored_item.get("engagement", {}).get("points", 0) > 500:
        bonus += BONUSES.get("high_engagement", 0.5)

    if scored_item.get("builder_type") == "indie":
        bonus += BONUSES.get("indie_builder", 0.5)

    if scored_item.get("source") in ("hackernews", "github_trending"):
        bonus += BONUSES.get("trusted_source", 0.3)

    scored_item["score"] = min(10.0, round(original_score + bonus, 1))
    scored_item["bonus_applied"] = round(bonus, 1)
