"""
Taste profile updater — weekly recalculation of personal preferences.
Runs every Sunday via GitHub Actions or manually via `make taste-update`.
Analyzes all thumbs up/down feedback and rebuilds the preference profile.
"""

import json
from datetime import datetime, timezone
from collections import Counter
from src.config import FEEDBACK_PATH
from src.utils.logger import get_logger

log = get_logger("feedback.taste_updater")


def recalculate_full_profile():
    """
    Full taste profile recalculation from all feedback history.
    More thorough than the basic version in taste_model.py —
    this one also extracts keyword patterns and builder preferences.
    """
    data = _load_feedback()
    thumbs_up = data.get("thumbs_up", [])
    thumbs_down = data.get("thumbs_down", [])
    total = len(thumbs_up) + len(thumbs_down)

    if total < 5:
        log.info("insufficient_feedback", total=total)
        return

    log.info("recalculating_taste", up=len(thumbs_up), down=len(thumbs_down))

    # ── Category analysis ──
    cat_up = Counter(item.get("category", "other") for item in thumbs_up)
    cat_down = Counter(item.get("category", "other") for item in thumbs_down)

    # Net preference score per category
    all_cats = set(list(cat_up.keys()) + list(cat_down.keys()))
    cat_net = {}
    for cat in all_cats:
        up_count = cat_up.get(cat, 0)
        down_count = cat_down.get(cat, 0)
        total_cat = up_count + down_count
        if total_cat > 0:
            cat_net[cat] = (up_count - down_count) / total_cat  # Range: -1 to 1

    preferred = [cat for cat, score in sorted(cat_net.items(), key=lambda x: -x[1]) if score > 0.2][:5]
    disliked = [cat for cat, score in sorted(cat_net.items(), key=lambda x: x[1]) if score < -0.2][:5]

    # ── Keyword extraction ──
    up_keywords = Counter()
    down_keywords = Counter()

    for item in thumbs_up:
        for kw in item.get("keywords", []):
            up_keywords[kw.lower()] += 1

    for item in thumbs_down:
        for kw in item.get("keywords", []):
            down_keywords[kw.lower()] += 1

    # Keywords that appear 2+ times in liked items and not in disliked
    keyword_boosts = [
        kw for kw, count in up_keywords.most_common(20)
        if count >= 2 and down_keywords.get(kw, 0) < count * 0.5
    ][:10]

    keyword_penalties = [
        kw for kw, count in down_keywords.most_common(20)
        if count >= 2 and up_keywords.get(kw, 0) < count * 0.5
    ][:10]

    # ── Builder type preferences ──
    builder_up = Counter(item.get("builder_type", "") for item in thumbs_up if item.get("builder_type"))
    preferred_builders = [bt for bt, _ in builder_up.most_common(3)]

    # ── Score preference (do they prefer high-scoring items?) ──
    up_scores = [item.get("score", 0) for item in thumbs_up if item.get("score")]
    avg_liked_score = sum(up_scores) / len(up_scores) if up_scores else 0

    # ── Build profile ──
    profile = {
        "preferred_categories": preferred,
        "disliked_categories": disliked,
        "keyword_boosts": keyword_boosts,
        "keyword_penalties": keyword_penalties,
        "preferred_builders": preferred_builders,
        "total_feedback": total,
        "avg_liked_score": round(avg_liked_score, 1),
        "category_net_scores": {k: round(v, 2) for k, v in cat_net.items()},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    data["taste_profile"] = profile
    _save_feedback(data)

    log.info(
        "taste_profile_updated",
        total_feedback=total,
        preferred_categories=preferred,
        disliked_categories=disliked,
        keyword_boosts=keyword_boosts[:5],
    )

    return profile


def get_taste_evolution() -> dict:
    """
    Compare current taste profile to what it was before.
    Useful for monthly reports: "You're watching more X and less Y."
    """
    data = _load_feedback()
    profile = data.get("taste_profile", {})

    # Simple evolution: count feedback by month
    monthly_cats: dict[str, Counter] = {}
    for item in data.get("thumbs_up", []):
        date = item.get("date", "")[:7]  # YYYY-MM
        if date:
            monthly_cats.setdefault(date, Counter())[item.get("category", "other")] += 1

    return {
        "current_preferences": profile.get("preferred_categories", []),
        "monthly_interest": {month: dict(cats) for month, cats in sorted(monthly_cats.items())},
    }


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
