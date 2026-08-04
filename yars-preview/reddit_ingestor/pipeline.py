"""Pipeline orchestrator — ties scraping, processing, and storage together."""

from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from reddit_ingestor.config import (
    JSON_OUTPUT,
    MAX_COMMENTS,
    POST_LIMIT,
    SQLITE_OUTPUT,
    SUBREDDITS,
)
from reddit_ingestor.models import Post, ScrapeStats
from reddit_ingestor.processor.cleaner import clean_posts
from reddit_ingestor.processor.deduplicator import deduplicate_posts
from reddit_ingestor.scraper.base import BaseScraper
from reddit_ingestor.storage.json_writer import write_json
from reddit_ingestor.storage.sqlite_writer import write_sqlite


def _scrape_subreddit(
    scraper: BaseScraper,
    subreddit: str,
    stats: ScrapeStats,
) -> list[Post]:
    """Scrape a single subreddit: fetch posts, then hydrate comments."""
    raw_posts = scraper.fetch_subreddit_posts(subreddit, limit=POST_LIMIT)
    stats.posts_fetched += len(raw_posts)

    posts: list[Post] = []
    for raw in raw_posts:
        full = scraper.fetch_post(raw.post_id)
        if full is None:
            stats.posts_skipped += 1
            continue
        # Limit comments
        limited_comments = full.comments[:MAX_COMMENTS]
        post = Post(
            post_id=full.post_id,
            subreddit=full.subreddit,
            title=full.title,
            selftext=full.selftext,
            score=full.score,
            author=full.author,
            created_utc=full.created_utc,
            url=full.url,
            flair=full.flair,
            comments=limited_comments,
        )
        stats.comments_fetched += len(full.comments)
        stats.comments_kept += len(limited_comments)
        posts.append(post)

    return posts


def run_pipeline(
    scraper: BaseScraper,
    *,
    subreddits: list[str] | None = None,
    json_path: Path | None = None,
    sqlite_path: Path | None = None,
) -> tuple[list[Post], ScrapeStats]:
    """Execute the full ingestion pipeline.

    Steps per subreddit:
      1. Fetch newest posts
      2. Fetch full post details + comments
      3. Clean (filter deleted/short/AutoModerator)
      4. Deduplicate
      5. Write JSON
      6. Write SQLite

    Args:
        scraper: Any ``BaseScraper`` implementation.
        subreddits: Override the default subreddit list.
        json_path: Override the default JSON output path.
        sqlite_path: Override the default SQLite output path.

    Returns:
        A tuple of (final posts, aggregated stats).
    """
    targets = subreddits or SUBREDDITS
    jpath = json_path or JSON_OUTPUT
    spath = sqlite_path or SQLITE_OUTPUT
    stats = ScrapeStats()

    all_posts: list[Post] = []
    for i, name in enumerate(targets):
        if i > 0:
            # Pause between subreddits to avoid rate limiting
            logger.info("Pausing 10s between subreddits...")
            time.sleep(10)
        logger.info(f"── Processing r/{name} ──")
        posts = _scrape_subreddit(scraper, name, stats)
        all_posts.extend(posts)
        stats.subreddits_processed += 1

    logger.info(f"Total raw posts collected: {len(all_posts)}")

    # Deduplicate across subreddits
    all_posts, dupes = deduplicate_posts(all_posts)
    stats.duplicates_removed = dupes

    # Clean
    all_posts = clean_posts(all_posts)

    # Persist
    write_json(all_posts, jpath)
    write_sqlite(all_posts, spath)

    return all_posts, stats
