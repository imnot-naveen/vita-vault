# Reddit Ingestion Pipeline — Architecture Document

## Overview

This is a production-quality Reddit ingestion pipeline designed to be the
**data collection layer** of a future RAG (Retrieval-Augmented Generation)
system. It fetches posts and comments from configured subreddits, cleans
and deduplicates the content, and persists it to JSON and SQLite.

The pipeline does **not** generate embeddings, query a vector database, or
serve an API. Its sole responsibility is to produce clean, structured
Reddit content ready for downstream processing.

---

## Project Structure

```
yars-preview/
├── pyproject.toml                  # uv project definition
├── ARCHITECTURE.md                 # This document
├── reddit_ingestor/                # The ingestion package
│   ├── __init__.py
│   ├── config.py                   # All configurable constants
│   ├── models.py                   # Domain dataclasses
│   ├── main.py                     # CLI entry point
│   ├── pipeline.py                 # Orchestrator
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract BaseScraper (ABC)
│   │   ├── reddit_scraper.py       # Direct JSON API via old.reddit.com
│   │   ├── praw_scraper.py         # PRAW + OAuth2
│   │   └── yars_scraper.py         # YARS library wrapper
│   ├── processor/
│   │   ├── __init__.py
│   │   ├── cleaner.py              # Filters deleted/AutoMod/short content
│   │   └── deduplicator.py         # Deduplicates by post_id
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── json_writer.py          # Exports to JSON
│   │   └── sqlite_writer.py        # Writes to SQLite with indexes
│   └── output/                     # Runtime output directory
│       ├── reddit_dump.json
│       ├── reddit_dump.db
│       └── ingestor.log
└── output/                         # (legacy YARS preview output)
```

---

## Architecture Decisions

### 1. Abstract Scraper Interface

**Decision:** Define a `BaseScraper` ABC with three methods:
`fetch_subreddit_posts()`, `fetch_post()`, `fetch_comments()`.

**Rationale:** Reddit can be accessed through many different mechanisms —
public JSON endpoints, the official OAuth2 API (PRAW), third-party
scrapers (YARS), headless browsers (Playwright), or proxy services. By
programming against an abstract interface, the pipeline never depends on
any specific scraper implementation. Swapping `RedditJSONScraper` for
`PRAWScraper` requires changing a single argument to `run_pipeline()` —
zero changes to the pipeline, processor, or storage code.

**Trade-off:** An extra layer of indirection. For a project of this size
the overhead is minimal, and the benefit is significant: the scraper is
the most fragile component (Reddit actively blocks scrapers), so the
ability to hot-swap it without touching the rest of the system is
critical.

### 2. Three Scraper Implementations

| Scraper | Backend | Auth Required | IP Restrictions |
|---|---|---|---|
| `RedditJSONScraper` | Direct HTTP to `old.reddit.com` | No | Blocks datacenter IPs after sustained use |
| `PRAWScraper` | PRAW library + OAuth2 | Yes (Reddit app credentials) | None — works from any IP |
| `YARSScraper` | YARS library | No | Same as raw requests |

**`RedditJSONScraper` (primary):** Talks directly to Reddit's public
`.json` endpoints via `old.reddit.com`. This domain is less aggressive
about blocking datacenter IPs than `www.reddit.com`. The scraper uses a
persistent `requests.Session` with cookies obtained from a homepage
visit ("session warming"). It does **not** retry on HTTP 403 (permanent
block) — only on 429 (rate limit). This prevents the retry loop from
making an IP ban worse.

**`PRAWScraper` (production recommended):** Uses Reddit's official OAuth2
API via PRAW. Requires creating a "script" type app at
reddit.com/prefs/apps and setting four environment variables. Works from
any IP including datacenters. This is the recommended scraper for
production use.

**`YARSScraper` (legacy):** Wraps the YARS library which provides a
Reddit-like API without authentication. Included for backward
compatibility with the original proof-of-concept.

### 3. Rate Limiting Strategy

Reddit aggressively rate-limits and IP-bans servers that make too many
requests. The pipeline implements a multi-layered defense:

**Random delays:** Each request is followed by a random sleep between
`MIN_DELAY_SECONDS` (3s) and `MAX_DELAY_SECONDS` (8s). This avoids
fixed-interval patterns that Reddit's anti-bot systems detect.

**Subreddit pauses:** A 10-second pause between subreddits prevents
burst patterns.

**429 handling:** When Reddit returns HTTP 429 (rate limited), the scraper
pauses for `HTTP_429_PAUSE_SECONDS` (60s) before retrying.

**No 403 retries:** HTTP 403 means the IP is blocked. Retrying a blocked
IP only makes the ban longer. The scraper raises `PermissionError`
immediately, giving the user a clear message about what to do.

**Exponential backoff:** On transient failures, the scraper waits
exponentially longer between retries (2s, 4s, 8s...) up to a configured
maximum.

**Conservative defaults:** `MAX_RETRIES` is set to 3 (not 5). Each retry
on a blocked endpoint risks extending the IP ban.

### 4. old.reddit.com vs www.reddit.com

**Finding:** Reddit's `www.reddit.com` and `api.reddit.com` JSON
endpoints return HTTP 403 from datacenter/cloud IPs regardless of
headers, User-Agent, TLS fingerprint, or authentication method. This was
verified by testing:

- Direct `requests` with browser User-Agent
- `cloudscraper` (Cloudflare bypass library)
- HTTP/2 via `httpx`
- SOCKS5 and HTTP proxies (free and paid)
- OAuth2 anonymous tokens
- PRAW with built-in test credentials
- `curl` from the command line
- Session cookies from homepage visits

All returned 403.

**Breakthrough:** `old.reddit.com` returns 200 for the same `.json`
endpoints from the same IP. This is likely because Reddit's newer
frontend (`www.reddit.com`) has stricter anti-bot measures while
`old.reddit.com` (the legacy interface) has more relaxed filtering.

**Caveat:** Even `old.reddit.com` will eventually block IPs that make
too many requests in succession. The conservative rate limiting (3-8s
between requests, 10s between subreddits) is essential.

### 5. Data Models

All models use Python `dataclasses` (not Pydantic) for zero external
dependency:

- **`Comment`** (frozen): `comment_id`, `post_id`, `author`, `body`,
  `score`, `created_utc`. Frozen to prevent accidental mutation after
  insertion into storage.

- **`Post`** (frozen): `post_id`, `subreddit`, `title`, `selftext`,
  `score`, `author`, `created_utc`, `url`, `flair`, `comments` (list of
  Comment). Includes a `num_comments` property for convenience.

- **`ScrapeStats`** (mutable): Accumulates pipeline statistics. Has a
  `merge()` method for combining stats from multiple scraper runs.

**Why not Pydantic:** Pydantic adds a heavy dependency for validation
that isn't needed here. The data comes from Reddit's JSON API which has
consistent structure. If validation becomes necessary (e.g., when
ingesting from unreliable sources), Pydantic can be added later without
changing the interface.

### 6. Cleaning Pipeline

The cleaner removes content that is useless for RAG:

- **AutoModerator comments:** Bot-generated, no informational value.
- **`[deleted]` / `[removed]`:** Content the author or moderators removed.
- **Short comments** (< `MIN_COMMENT_LENGTH` = 15 chars): Too short to
  provide meaningful context for retrieval.

The cleaner operates on comments only, not posts. A post with a deleted
selftext but valid title and comments is still useful for RAG (the title
provides retrieval context).

### 7. Deduplication

Deduplication is by `post_id` only. Reddit's listing endpoints can return
the same post in multiple paginated responses, and the same post can
appear across different subreddit queries if crossposted.

Comment-level deduplication happens inside the scraper (by body text) to
handle Reddit's "more comments" pagination which can repeat comments.

### 8. Storage: Dual JSON + SQLite

**JSON** (`reddit_dump.json`): Human-readable, easily consumable by
downstream tools (pandas, LangChain, LlamaIndex). Includes the full
post+comment hierarchy in a single file. Suitable for datasets under ~100K
posts.

**SQLite** (`reddit_dump.db`): Structured storage with indexes for
efficient querying. Schema:

```sql
CREATE TABLE posts (
    post_id     TEXT PRIMARY KEY,
    subreddit   TEXT NOT NULL,
    title       TEXT NOT NULL,
    selftext    TEXT NOT NULL,
    score       INTEGER NOT NULL,
    author      TEXT NOT NULL,
    created_utc REAL NOT NULL,
    url         TEXT NOT NULL,
    flair       TEXT
);

CREATE TABLE comments (
    comment_id  TEXT PRIMARY KEY,
    post_id     TEXT NOT NULL,
    author      TEXT NOT NULL,
    body        TEXT NOT NULL,
    score       INTEGER NOT NULL,
    created_utc REAL NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(post_id)
);
```

Indexes on `subreddit`, `created_utc`, and `post_id` for fast queries.
`INSERT OR IGNORE` prevents duplicate inserts when re-running the
pipeline.

**Why both:** JSON is the interchange format (easy to inspect, transform,
and feed into ML pipelines). SQLite is the queryable store (fast
aggregations, filtering, joins). A production system might replace JSON
with a message queue and SQLite with PostgreSQL, but the dual-output
approach covers most use cases.

### 9. Configuration

All constants live in `config.py` with sensible defaults. No `.env` file
parser is used — Reddit OAuth credentials are read from environment
variables via `os.getenv()`, which is the standard 12-factor app
approach.

The configuration is structured in sections:
- Target subreddits and scraper parameters
- Network settings (proxy, timeout, User-Agent)
- Reddit OAuth2 credentials
- Rate limiting parameters
- Output paths

### 10. CLI Interface

```
python -m reddit_ingestor.main --scraper reddit    # Default: direct JSON
python -m reddit_ingestor.main --scraper praw      # OAuth2 via PRAW
python -m reddit_ingestor.main --scraper yars      # YARS library
```

The `--scraper` flag selects the backend. This could be extended to
`--config path/to/config.py` for full configurability, but environment
variables and hardcoded defaults cover the current use case.

---

## Pipeline Flow

```
For each configured subreddit:
  │
  ├─ fetch_subreddit_posts(subreddit, limit=20)
  │   └─ Returns Post objects with empty comments
  │
  ├─ For each post:
  │   └─ fetch_post(post_id)
  │       └─ Returns hydrated Post with comments
  │       └─ Comments limited to MAX_COMMENTS (20)
  │
  └─ 10s pause between subreddits
  │
After all subreddits:
  │
  ├─ deduplicate_posts()     — Remove duplicate post_ids
  ├─ clean_posts()           — Filter bad comments
  ├─ write_json()            — Export to reddit_dump.json
  └─ write_sqlite()          — Write to reddit_dump.db
```

---

## Data Flow Diagram

```
Reddit API ──→ Scraper ──→ Pipeline ──→ Processor ──→ Storage
   │                │           │            │            │
   │  old.reddit    │  raw      │  raw       │  clean     │  json
   │  .json         │  Posts    │  Posts     │  Posts     │  sqlite
   │  endpoints     │           │            │            │
   └────────────────┘           └────────────┘            │
                                                          │
                                                    output/
                                                    ├── reddit_dump.json
                                                    ├── reddit_dump.db
                                                    └── ingestor.log
```

---

## Running the Pipeline

### Prerequisites

- Python 3.12+
- `uv` package manager (recommended) or `pip`

### Installation

```bash
uv sync
# or
pip install yars loguru
```

### Quick Start

```bash
# Direct JSON scraping (works from residential IPs)
python -m reddit_ingestor.main

# With Reddit OAuth2 (works from any IP)
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
export REDDIT_USERNAME="your_username"
export REDDIT_PASSWORD="your_password"
python -m reddit_ingestor.main --scraper praw
```

### Expected Output

```
=======================================================
  REDDIT INGESTION STATISTICS
=======================================================
  Subreddits processed  : 3
  Posts fetched          : 60
  Posts skipped          : 0
  Comments fetched       : 505
  Comments kept          : 402
  Duplicates removed     : 0
  Avg comments/post      : 6.7
-------------------------------------------------------
  JSON size              : 0.21 MB
  SQLite size            : 0.21 MB
  Runtime                : 78.0s
=======================================================
```

---

## Known Limitations

1. **IP blocking from datacenters.** Reddit blocks `www.reddit.com` JSON
   endpoints from cloud/datacenter IPs. `old.reddit.com` works but will
   eventually block sustained high-volume scraping. For production use,
   the PRAW scraper with OAuth2 is recommended.

2. **No incremental scraping.** Each run fetches the newest N posts from
   scratch. There is no "last seen" cursor to resume where a previous
   run left off. This is intentional for the prototype — a production
   system would add cursor persistence.

3. **No post-level filtering.** The pipeline fetches all posts from the
   configured subreddits. There is no filtering by score, age, or
   content type. This keeps the ingestion layer simple and lets
   downstream consumers apply their own filters.

4. **Comment tree depth.** Reddit comment trees can be arbitrarily deep.
   The scraper recursively traverses all reply levels but caps the total
   comments per post at `MAX_COMMENTS`.

5. **No media handling.** The pipeline stores text content only. Images,
   videos, and links are recorded as URLs but not downloaded or
   processed. This is appropriate for a text-based RAG system.

---

## Future Enhancements

- **Incremental scraping:** Persist `after` cursors per subreddit to
  avoid re-fetching known posts.
- **Content chunking:** Split long selftext and comments into
  RAG-appropriate chunks with overlap.
- **Embedding generation:** Feed cleaned content into a sentence
  transformer model.
- **Vector storage:** Insert embeddings into Qdrant or Pinecone.
- **Monitoring:** Add Prometheus metrics for scrape rate, error rate,
  and content volume.
- **Playwright scraper:** For subreddits that require JavaScript
  rendering.
- **Proxy rotation:** Automatic proxy selection from a pool.
