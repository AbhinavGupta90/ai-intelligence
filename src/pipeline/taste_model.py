"""
Personal taste model — learns from thumbs up/down feedback.
Adjusts scores based on category preferences and keyword affinity.
"""

import json
from pathlib import Path
from src.config import FEEDBACK_PATH, TASTE_CFG
from src.utils.logger import get_logger

log = get_logger("pipeline.taste")


def load_taste_profile() -> dict:
    """Load the current taste profile from feedback.json."""
    if not FEEDBACK_PATH.exists():
        return _default_profile()

    try:
        with open(FEEDBACK_PATH, "r") as f:
            data = json.load(f)
        return data.get("taste_profile", _default_profile())
    except (json.JSONDecodeError, KeyError):
        return _default_profile()


def apply_taste_adjustments(items: list[dict]) -> list[dict]:
    """
    Adjust scores based on personal taste profile.
    Only activates after min_feedback_to_activate threshold.
    """
    if not TASTE_CFG.get("enabled", True):
        return items

    profile = load_taste_profile()
    feedback_count = profile.get("total_feedback", 0)

    if feedback_count < TASTE_CFG.get("min_feedback_to_activate", 20):
        log.info("taste_inactive", feedback_count=feedback_count, min_required=TASTE_CFG["min_feedback_to_activate"])
        return items

    boost = TASTE_CFG.get("boost_amount", 0.5)
    penalty = TASTE_CFG.get("penalty_amount", -0.5)

    preferred_cats = set(profile.get("preferred_categories", []))
    disliked_cats = set(profile.get("disliked_categories", []))
    keyword_boosts = set(profile.get("keyword_boosts", []))
    keyword_penalties = set(profile.get("keyword_penalties", []))
    preferred_builders = set(profile.get("preferred_builders", []))

    adjusted_count = 0
    for item in items:
        adjustment = 0
        category = item.get("category", "")
        builder_type = item.get("builder_type", "")
        title_lower = item.get("title", "").lower()
        summary_lower = item.get("summary", "").lower()
        combined = f"{title_lower} {summary_lower}"

        # Category preference
        if category in preferred_cats:
            adjustment += boost
        elif category in disliked_cats:
            adjustment += penalty

        # Keyword affinity
        for kw in keyword_boosts:
            if kw in combined:
                adjustment += boost * 0.5  # Half boost per keyword
                break  # Only one keyword boost per item

        for kw in keyword_penalties:
            if kw in combined:
                adjustment += penalty * 0.5
                break

        # Builder type preference
        if builder_type in preferred_builders:
            adjustment += boost * 0.3

        if adjustment != 0:
            item["taste_adjustment"] = round(adjustment, 2)
            item["score"] = round(min(max(item.get("score", 0) + adjustment, 0), 10.0), 1)
            adjusted_count += 1

    log.info("taste_applied", adjusted=adjusted_count, total=len(items))

    # Re-sort by adjusted score
    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return items


def recalculate_taste_profile():
    """
    Recalculate taste profile from all feedback data.
    Run weekly (Sunday) via the scheduler.
    """
    if not FEEDBACK_PATH.exists():
        log.info("no_feedback_data")
        return

    with open(FEEDBACK_PATH, "r") as f:
        data = json.load(f)

    thumbs_up = data.get("thumbs_up", [])
    thumbs_down = data.get("thumbs_down", [])
    total = len(thumbs_up) + len(thumbs_down)

    if total < 10:
        log.info("insufficient_feedback", total=total)
        return

    # Count category preferences
    cat_scores: dict[str, float] = {}
    for item in thumbs_up:
        cat = item.get("category", "other")
        cat_scores[cat] = cat_scores.get(cat, 0) + 1

    for item in thumbs_down:
        cat = item.get("category", "other")
        cat_scores[cat] = cat_scores.get(cat, 0) - 1

    # Top preferred and disliked categories
    sorted_cats = sorted(cat_scores.items(), key=lambda x: x[1], reverse=True)
    preferred = [cat for cat, score in sorted_cats if score > 0][:5]
    disliked = [cat for cat, score in sorted_cats if score < 0][:5]

    # Extract keyword patterns from liked items
    keyword_freq: dict[str, int] = {}
    for item in thumbs_up:
        for kw in item.get("keywords", []):
            keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

    keyword_boosts = [kw for kw, count in sorted(keyword_freq.items(), key=lambda x: -x[1]) if count >= 2][:10]

    # Builder type preferences
    builder_freq: dict[str, int] = {}
    for item in thumbs_up:
        bt = item.get("builder_type", "")
        if bt:
            builder_freq[bt] = builder_freq.get(bt, 0) + 1

    preferred_builders = [bt for bt, _ in sorted(builder_freq.items(), key=lambda x: -x[1])][:3]

    # Save updated profile
    from datetime import datetime, timezone
    profile = {
        "preferred_categories": preferred,
        "disliked_categories": disliked,
        "keyword_boosts": keyword_boosts,
        "keyword_penalties": [],  # TODO: extract from thumbs_down keywords
        "preferred_builders": preferred_builders,
        "total_feedback": total,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    data["taste_profile"] = profile
    with open(FEEDBACK_PATH, "w") as f:
        json.dump(data, f, indent=2)

    log.info("taste_recalculated", total_feedback=total, preferred=preferred, disliked=disliked)


def _default_profile() -> dict:
    return {
        "preferred_categories": [],
        "disliked_categories": [],
        "keyword_boosts": [],
        "keyword_penalties": [],
        "preferred_builders": [],
        "total_feedback": 0,
    }
