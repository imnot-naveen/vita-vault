"""Entry point for the Reddit ingestion pipeline."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from loguru import logger

from reddit_ingestor.config import LOG_FILE, OUTPUT_DIR, SUBREDDITS
from reddit_ingestor.models import ScrapeStats
from reddit_ingestor.pipeline import run_pipeline
from reddit_ingestor.scraper.base import BaseScraper


def _setup_logging() -> None:
    """Configure loguru for console + rotating file output."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level="INFO",
    )
    logger.add(
        str(LOG_FILE),
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
        level="DEBUG",
        rotation="10 MB",
    )


def _print_stats(stats: ScrapeStats, elapsed: float, json_size_mb: float) -> None:
    """Print a formatted statistics summary to stdout."""
    sqlite_path = OUTPUT_DIR / "reddit_dump.db"
    sqlite_size_mb = (
        sqlite_path.stat().st_size / (1024 * 1024) if sqlite_path.exists() else 0.0
    )
    json_path = OUTPUT_DIR / "reddit_dump.json"
    json_actual = json_path.stat().st_size / (1024 * 1024) if json_path.exists() else 0.0

    avg_comments = (
        stats.comments_kept / stats.posts_fetched
        if stats.posts_fetched > 0
        else 0.0
    )

    print()
    print("=" * 55)
    print("  REDDIT INGESTION STATISTICS")
    print("=" * 55)
    print(f"  Subreddits processed  : {stats.subreddits_processed}")
    print(f"  Posts fetched          : {stats.posts_fetched}")
    print(f"  Posts skipped          : {stats.posts_skipped}")
    print(f"  Comments fetched       : {stats.comments_fetched}")
    print(f"  Comments kept          : {stats.comments_kept}")
    print(f"  Duplicates removed     : {stats.duplicates_removed}")
    print(f"  Avg comments/post      : {avg_comments:.1f}")
    print("-" * 55)
    print(f"  JSON size              : {json_actual:.2f} MB")
    print(f"  SQLite size            : {sqlite_size_mb:.2f} MB")
    print(f"  Runtime                : {elapsed:.1f}s")
    print("=" * 55)


def _build_scraper(name: str) -> BaseScraper:
    """Instantiate a scraper by name.

    Args:
        name: One of ``"reddit"``, ``"praw"``, or ``"yars"``.

    Returns:
        A ``BaseScraper`` implementation.
    """
    if name == "praw":
        from reddit_ingestor.scraper.praw_scraper import PRAWScraper

        return PRAWScraper()
    if name == "yars":
        from reddit_ingestor.scraper.yars_scraper import YARSScraper

        return YARSScraper()
    from reddit_ingestor.scraper.reddit_scraper import RedditJSONScraper

    return RedditJSONScraper()


def main() -> int:
    """Run the full ingestion pipeline."""
    parser = argparse.ArgumentParser(description="Reddit ingestion pipeline")
    parser.add_argument(
        "--scraper",
        choices=["reddit", "praw", "yars"],
        default="reddit",
        help="Scraper backend (default: reddit)",
    )
    args = parser.parse_args()

    _setup_logging()

    logger.info("Starting Reddit ingestion pipeline")
    logger.info(f"Target subreddits: {SUBREDDITS}")
    logger.info(f"Scraper backend: {args.scraper}")

    start = time.monotonic()

    try:
        scraper = _build_scraper(args.scraper)
        posts, stats = run_pipeline(scraper)
    except Exception as exc:
        logger.exception(f"Pipeline failed: {exc}")
        return 1

    elapsed = time.monotonic() - start

    if not posts:
        logger.warning("No posts collected")
        return 1

    json_path = OUTPUT_DIR / "reddit_dump.json"
    json_size_mb = (
        json_path.stat().st_size / (1024 * 1024) if json_path.exists() else 0.0
    )

    _print_stats(stats, elapsed, json_size_mb)
    logger.info("Ingestion pipeline completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
