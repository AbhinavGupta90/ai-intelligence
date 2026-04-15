"""
Configuration loader -- reads config.yml and environment variables.
All tuneable parameters live in config.yml, secrets in .env/GitHub Secrets.
"""
import os
import yaml
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "config.yml"

def load_yaml_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

_cfg = load_yaml_config()

# Environment variables (secrets)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
PRODUCTHUNT_API_TOKEN = os.getenv("PRODUCTHUNT_API_TOKEN", "")

# Configuration from yaml
DRY_RUN = _cfg.get("dry_run", False)
MAX_DAILY_ITEMS = _cfg.get("max_daily_items", 15)
BATCH_SIZE = _cfg.get("batch_size", 5)
BONUSES = _cfg.get("bonuses", {})

SOURCES_CFG = _cfg.get("sources", {})
SCORING_CFG = _cfg.get("scoring", {})
DELIVERY_CFG = _cfg.get("delivery", {})
TASTE_CFG = _cfg.get("taste", {})

# Velocity detection config
VELOCITY_WINDOW_HOURS = _cfg.get("velocity", {}).get("window_hours", 6)
VELOCITY_ALERT_PERCENTILE = _cfg.get("velocity", {}).get("alert_percentile", 95)

# Alert config
MIN_SCORE_ALERT = _cfg.get("alerts", {}).get("min_score", 8.0)
MAX_REALTIME_ALERTS = _cfg.get("alerts", {}).get("max_per_day", 5)

# Data directories
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
FEEDBACK_PATH = DATA_DIR / "feedback.json"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
