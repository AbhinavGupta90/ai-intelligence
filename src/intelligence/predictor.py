"""
Trend predictor — generates predictions based on category velocity and patterns.
Uses LLM (Gemini free / Anthropic paid) to synthesize data into forward-looking insights.
"""

import json
from datetime import datetime, timezone
from src.config import KNOWLEDGE_DIR
from src.intelligence.trend_tracker import get_category_trends, get_category_sparklines
from src.intelligence.builder_tracker import get_builder_stats
from src.intelligence.project_tracker import get_project_stats, get_breakout_projects
from src.utils.llm import generate as llm_generate, get_backend
from src.utils.logger import get_logger

log = get_logger("intelligence.predictor")

PREDICTIONS_PATH = KNOWLEDGE_DIR / "predictions.json"


async def generate_predictions() -> list[dict]:
    """
    Generate trend predictions based on accumulated data.
    Returns list of prediction dicts with confidence levels.
    """
    backend = get_backend()
    if backend == "none":
        log.warning("no_llm_backend", msg="Cannot generate predictions without LLM API key")
        return []

    # Gather context
    trends = get_category_trends(weeks_back=4)
    sparklines = get_category_sparklines(weeks=8)
    breakouts = get_breakout_projects()
    builder_stats = get_builder_stats()
    project_stats = get_project_stats()

    context = {
        "rising_categories": trends.get("rising", []),
        "declining_categories": trends.get("declining", []),
        "new_categories": trends.get("new", []),
        "hot_streak": trends.get("hot_streak"),
        "sparklines": sparklines,
        "breakout_projects": breakouts,
        "builder_stats": builder_stats,
        "project_stats": project_stats,
    }

    try:
        system_prompt = """You are an AI trend analyst making predictions based on data.
Be specific, opinionated, and actionable. Give 2-3 predictions with confidence levels.
Format as JSON array: [{"prediction": "...", "confidence": "high|medium|low", "timeframe": "1-2 weeks", "reasoning": "..."}]
Return ONLY valid JSON."""

        content = await llm_generate(
            prompt=f"Based on this AI builder ecosystem data, generate 2-3 predictions about what will trend next:\n{json.dumps(context, indent=2)}",
            system=system_prompt,
            max_tokens=500,
        )

        if not content:
            log.warning("prediction_empty", msg="LLM returned empty response")
            return []

        # Handle potential markdown wrapping
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        predictions = json.loads(content)

        # Save predictions for later scorecard
        _save_predictions(predictions)

        log.info("predictions_generated", count=len(predictions), backend=backend)
        return predictions

    except Exception as e:
        log.warning("prediction_failed", error=str(e))
        return []


def get_prediction_scorecard() -> list[dict]:
    """
    Load past predictions and check how they fared.
    Called in monthly reports to track prediction accuracy.
    """
    data = _load_json(PREDICTIONS_PATH, {"history": []})
    return data.get("history", [])[-10:]  # Last 10 prediction batches


def _save_predictions(predictions: list[dict]):
    """Append predictions to history for future scoring."""
    data = _load_json(PREDICTIONS_PATH, {"history": []})
    data["history"].append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "predictions": predictions,
        "scored": False,  # Will be scored in monthly report
    })
    # Keep last 26 entries (6 months of weekly predictions)
    data["history"] = data["history"][-26:]
    _save_json(PREDICTIONS_PATH, data)


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return default


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
