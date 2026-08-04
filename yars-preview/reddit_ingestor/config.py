"""Configuration constants for the Reddit ingestion pipeline."""

import os
from pathlib import Path

# ── Target subreddits ────────────────────────────────────────────────
SUBREDDITS: list[str] = [
    "vita",
    "vitahacks",
    "vitapiracy",
]

# ── Scraper parameters ───────────────────────────────────────────────
POST_LIMIT: int = 20
MAX_COMMENTS: int = 20
MIN_COMMENT_LENGTH: int = 15

# ── Network ──────────────────────────────────────────────────────────
# Set to e.g. "http://127.0.0.1:1080" or "socks5://127.0.0.1:1080" if
# Reddit blocks your IP (common on cloud/datacenter servers).
PROXY_URL: str | None = None

REQUEST_TIMEOUT: int = 15

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ── Reddit OAuth2 (for PRAW scraper) ────────────────────────────────
# Create a "script" type app at https://www.reddit.com/prefs/apps
# Then set these environment variables or fill them in directly.
REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME: str = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD: str = os.getenv("REDDIT_PASSWORD", "")
REDDIT_USER_AGENT: str = "python:vita-vault:v0.1.0 (by /u/vita-vault-bot)"

# ── Rate limiting ────────────────────────────────────────────────────
MIN_DELAY_SECONDS: float = 3.0
MAX_DELAY_SECONDS: float = 8.0
BACKOFF_BASE: float = 2.0
BACKOFF_MAX_SECONDS: float = 60.0
MAX_RETRIES: int = 3
HTTP_429_PAUSE_SECONDS: float = 60.0

# ── Output paths ─────────────────────────────────────────────────────
OUTPUT_DIR: Path = Path("reddit_ingestor/output")
JSON_OUTPUT: Path = OUTPUT_DIR / "reddit_dump.json"
SQLITE_OUTPUT: Path = OUTPUT_DIR / "reddit_dump.db"
LOG_FILE: Path = OUTPUT_DIR / "ingestor.log"
