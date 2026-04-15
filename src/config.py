"""
Configuration loader — reads config.yml and environment variables.
All tuneable parameters live in config.yml, secrets in .env/GitHub Secrets.
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Project root = parent of src/
ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "config.yml"


def load_yaml_config() -> dict:
    """Load and return the YAML configuration file."""
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


_cfg = load_yaml_config()


# ── General ──────────────────────────────────────────────
TIMEZONE = _cfg["general"]["timezone"]
DAILY_DIGEST_TIME = _cfg["general"]["daily_digest_time"]
REALTIME_CHECK_HOURS = _cfg["general"]["realtime_check_interval_hours"]
MAX_DAILY_ITEMS = _cfg["general"]["max_daily_items"]
MAX_REALTIME_ALERTS = _cfg["general"]["max_realtime_alerts_per_day"]
DRY_RUN = _cfg["general"].get("dry_run", False)

# ── Sources ──────────────────────────────────────────────
SOURCES_CFG = _cfg["sources"]

# ── Scoring ──────────────────────────────────────────────
SCORING_CFG = _cfg["scoring"]
SCORE_WEIGHTS = SCORING_CFG["weights"]
MIN_SCORE_DELIVER = SCORING_CFG["min_score_to_deliver"]
MIN_SCORE_ALERT = SCORING_CFG["min_score_for_alert"]
BATCH_SIZE = SCORING_CFG["batch_size"]
BONUSES = SCORING_CFG["bonuses"]

# ── Velocity ─────────────────────────────────────────────
VELOCITY_WINDOW_HOURS = _cfg["velocity"]["window_hours"]
VELOCITY_ALERT_PERCENTILE = _cfg["velocity"]["alert_percentile"]

# ── Taste Model ──────────────────────────────────────────
TASTE_CFG = _cfg["taste_model"]

# ── Delivery ─────────────────────────────────────────────
DELIVERY_CFG = _cfg["delivery"]

# ── Reports ──────────────────────────────────────────────
REPORTS_CFG = _cfg["reports"]

# ── Persistence ──────────────────────────────────────────
PERSISTENCE_CFG = _cfg["persistence"]

# ── Error Handling ───────────────────────────────────────
ERROR_CFG = _cfg["error_handling"]

# ── Secrets (from environment) ───────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")              # FREE — primary LLM (Llama 3.3 70B)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")    # Paid — fallback LLM backend
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
PRODUCTHUNT_API_TOKEN = os.getenv("PRODUCTHUNT_API_TOKEN", "")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# ── Paths ────────────────────────────────────────────────
KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
LOGS_DIR = ROOT_DIR / "logs"
FEEDBACK_PATH = ROOT_DIR / "feedback.json"

# Ensure directories exist
KNOWLEDGE_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
