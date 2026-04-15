# 🧠 AI Intelligence Digest

A self-improving daily AI intelligence system that finds the most interesting things people are building with AI — learns your taste over time, spots trends before they go mainstream, and delivers actionable insights via Telegram.

**Signal over noise.** 10,000+ posts scanned daily → 10 gems delivered to your Telegram at 6 AM.

## Features

- **9 sources**: Reddit (6 subs), Hacker News, GitHub Trending, Product Hunt, Arxiv, Dev.to, Hugging Face, Twitter/X, YouTube
- **4-layer filtering**: Rule-based pre-filter → Velocity detection → Claude Sonnet scoring → Fuzzy dedup
- **Smart scoring**: Novelty (35%) + Techn�cal Depth (25%) + Wow Factor (25%) + Practical Value (15%)
- **Per-item feedback**: Every item gets its own 👍/👎 buttons — the system learns YOUR taste
- **Trend intelligence**: Category trends, builder tracking, project momentum, AI-generated predictions
- **Source health monitoring**: Tracks source reliability, alerts you when a source fails 3+ days in a row
- **Real-time alerts**: Items scoring 9.5+ sent immediately, don't wait for morning digest
- **Reports**: Weekly intelligence brief (Sunday) + Monthly deep dive (1st of month)
- **Zero daily effort**: Runs on GitHub Actions. Fire and forget.

## Quick Start (5 minutes)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/ai-intelligence.git
cd ai-intelligence
pip install -r requirements.txt
```

### 2. Set up secrets

```bash
cp .env.example .env
# Edit .env with your keys (minimum required):
#   ANTHROPIC_API_KEY   — Claude API for scoring
#   TELEGRAM_BOT_TOKEN  — create via @BotFather
#   TELEGRAM_CHAT_ID    — find via @userinfobot
```

### 3. Test locally

```bash
# Dry run — fetches, filters, scores, prints to console (no Telegram)
make dry-run

# Test a single source
make test-source SOURCE=reddit

# Full run with Telegram delivery
make run
```

### 4. Deploy to GitHub Actions

```bash
# Add secrets to your GitHub repo:
# Settings → Secrets → Actions → New repository secret
# Required: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# Optional: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, PRODUCTHUNT_API_TOKEN,
#           TWITTER_BEARER_TOKEN, YOUTUBE_API_KEY

git push origin main
# GitHub Actions runs automatically:
#   Daily digest   → 6:00 AM IST
#   Alert checks   → every 4 hours
#   Weekly report  → Sunday 9:00 AM IST
#   Monthly report → 1st of month 9:00 AM IST
```

### 5. Deploy feedback bot (optional)

The feedback bot handles 👍/👎 button presses in real-time. Deploy to any always-on service:

```bash
# Railway
railway up

# Render (set start command to):
python run_bot.py

# Docker
docker build -t ai-intel-bot .
docker run -e TELEGRAM_BOT_TOKEN=your_token ai-intel-bot
```

## Usage

```bash
make run              # Full daily digest
make dry-run          # Test without Telegram
make alert            # Real-time alert check
make weekly           # Weekly intelligence report
make monthly          # Monthly deep dive
make feedback         # Start feedback bot (long-polling)
make taste-update     # Recalculate taste profile
make debug            # Verbose debug run
```

### CLI flags

```bash
python -m src.main --mode daily --dry-run       # Dry run
python -m src.main --source reddit --debug      # Single source + debug
python -m src.main --mode weekly                # Weekly report
python -m src.main --mode alert                 # Alert check
python -m src.main --mode feedback              # Feedback bot
python -m src.main --mode taste-update          # Recalculate preferences
```

## Architecture

```
Sources (parallel) →  Pre-Filter →  Velocity →  Claude Scorer  →  Dedup  →  Taste  →  Telegram
  Reddit                Rule-based     Detect       Batched API       Fuzzy      Learn     Per-item
  HN                    80% cut        outliers     Sonnet 4          Match      Adjust    messages
  GitHub Trending                      flag 🚀     Weighted score                          + 👍/👎
  Product Hunt
  Arxiv                                    ↓
  Dev.to                              Knowledge Graph ← builders.json, projects.json, categories.json
  HuggingFace                              ↓
  Twitter/X                           Intelligence → trend_tracker, predictor, builder_tracker
  YouTube                                  ↓
                                      Source Health → failure streaks, 3-day alerts
```

## Source Configuration

| Source | Auth Needed | Config Key | Default |
|---------|-------------|-------------|---------|
| Reddit | No (public JSON) | `sources.reddit` | ✅ Enabled |
| Hacker News | No (Algolia API) | `sources.hackernews` | ✅ Enabled |
| GitHub Trending | No (search API) | `sources.github_trending` | ✅ Enabled |
| Product Hunt | API Token (optional) | `sources.producthunt` | ✅ Enabled |
| Arxiv | No | `sources.arxiv` | ✅ Enabled |
| Dev.to | No (Forem API) | `sources.devto` | ✅ Enabled |
| Hugging Face | No (HF API) | `sources.huggingface` | ✅ Enabled |
| Twitter/X | Bearer Token | `sources.twitter` | ❌ Disabled |
| YouTube | API Key | `sources.youtube` | ❌ Disabled |

Enable Twitter/YouTube by setting `enabled: true` in `config.yml` and adding the API keys.

## Key Configuration

All settings in `config.yml` — no hardcoded magic numbers:

| Setting | Default | What it does |
|----------|-----------|-------------|
| `sources.reddit.min_upvotes` | 50 | Min Reddit upvotes to pass pre-filter |
| `scoring.min_score_to_deliver` | 8.0 | Score threshold for daily digest |
| `scoring.min_score_for_alert` | 9.5 | Score threshold for real-time alerts |
| `general.max_daily_items` | 10 | Max items per daily digest |
| `taste_model.min_feedback_to_activate` | 20 | Feedback count before taste kicks in |
| `velocity.window_hours` | 6 | Window for velocity calculation |

## Intelligence Features

### Source Health Dashboard
Tracks per-source reliability. If a source fails 3+ consecutive days, you get a separate Telegram alert with diagnostics. Health status appears in the daily digest footer.

### Trend Predictions
Every Sunday, Claude analyzes your accumulated data and generates 2-3 predictions about what will trend next, with confidence levels. Monthly reports include a prediction scorecard.

### Personal Taste Model
After 20+ thumbs up/down, the system builds a preference profile: preferred categories, keyword boosts/penalties, builder type preferences. Recalculated every Sunday. By month 2, expect 90%+ relevance.

### Knowledge Graph
Three persistent JSON files track compound intelligence:
- `builders.json` — recurring builders, their avg scores, and shipped projects
- `projects.json` — project momentum, cross-source mentions, score trends
- `categories.json` — weekly category snapshots with sparkline trend visualization

## Compound Value Timeline

- **Week 1-2**: Daily feed with scored items
- **Week 3-4**: Patterns emerge — "Voice AI is rising fast"
- **Month 2**: Taste model dialed — 90%+ relevance
- **Month 3**: Trend predictions start — "This category will blow up"
- **Month 6**: Unique personal AI trend database with 6 months of scored data

## Cost

| Component | Monthly Cost |
|-----------|-------------|
| Claude Sonnet API (~4 batch calls/day) | ~$2.50 |
| GitHub Actions (~10 min/day) | Free |
| Telegram Bot | Free |
| All public APIs | Free |
| Feedback bot hosting (Railway free tier) | Free |
| **Total** | **~$2.50** |

## Project Structure

```
ai-intelligence/
├── .github/workflows/
│   ├── daily-digest.yml           # Daily 6 AM IST
│   ├── realtime-alerts.yml        # Every 4 hours
│   └── weekly-monthly.yml         # Sunday + 1st of month
├── src/
│   ├── main.py                    # Orchestrator + CLI
│   ├── config.py                  # Config loader
│   ├── sources/                   # 9 data source fetchers
│   │   ├── reddit.py, hackernews.py, github_trending.py
│   │   ├── producthunt.py, arxiv.py, devto.py
│   │   └── huggingface.py, twitter.py, youtube.py
│   │   └── base.py               # Abstract source + SourceItem model
│   ├── pipeline/                  # 5-layer filtering engine
│   │   ├── pre_filter.py          # Rule-based noise elimination
│   │   ├── velocity.py            # Engagement velocity detection
│   │   ├── scorer.py              # Claude Sonnet LLM scoring
│   │   ├── dedup.py               # Fuzzy deduplication
│   │   └── taste_model.py         # Personal preference adjustments
│   ├── intelligence/              # Compound intelligence
│   │   ├── trend_tracker.py       # Category trends + sparklines
│   │   ├── builder_tracker.py     # Prolific + rising builders
│   │   ├── project_tracker.py     # Cross-source momentum
│   │   └── predictor.py           # AI trend predictions
│   ├── delivery/                  # Output formatting + sending
│   │   ├── telegram.py            # Per-item messages + feedback buttons
│   │   ├── alerts.py              # Real-time breakthrough alerts
│   │   ├── weekly_report.py       # Sunday intelligence report
│   │   └── monthly_report.py      # Monthly deep dive
│   ├── feedback/                  # Taste learning loop
│   │   ├── handler.py             # Telegram callback handler
│   │   └── taste_updater.py       # Weekly profile recalculation
│   ├── persistence/               # Data storage
│   │   ├── daily_log.py           # JSON + Markdown daily logs
│   │   ├── knowledge_graph.py     # Builders, projects, categories
│   │   ├── source_health.py       # Source reliability tracking
│   │   └── stats.py               # Pipeline statistics
│   └── utils/
│       ├── http_client.py         # Async HTTP with retries
│       ├── rate_limiter.py        # Per-source rate limiting
│       └── logger.py              # Structured JSON logging
├── knowledge/                     # Auto-populated knowledge base
├── logs/                          # Daily JSON + Markdown logs
├── run_bot.py                     # Standalone feedback bot (Railway/Render)
├── config.yml                     # All tuneable settings
├── feedback.json                  # Personal taste data
├── Dockerfile                     # Container deploy for feedback bot
├── Procfile                       # Railway/Render deploy
├── Makefile                       # Dev shortcuts
├── requirements.txt
└── .env.example
```

## Setting up Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, follow prompts → get your **bot token**
3. Search for **@userinfobot**, send `/start` → get your **chat ID**
4. Start a chat with your new bot (send any message so it can message you back)
5. Add both values to `.env` or GitHub Secrets

## License

MIT
