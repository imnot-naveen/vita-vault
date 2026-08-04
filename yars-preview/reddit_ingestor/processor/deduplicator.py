"""Deduplication processor for Reddit content."""

from __future__ import annotations

from loguru import logger

from reddit_ingestor.models import Post


def deduplicate_posts(posts: list[Post]) -> tuple[list[Post], int]:
    """Remove duplicate posts based on ``post_id``.

    Args:
        posts: List of posts that may contain duplicates.

    Returns:
        A tuple of (unique posts, number of duplicates removed).
    """
    seen: set[str] = set()
    unique: list[Post] = []
    duplicates = 0

    for post in posts:
        if post.post_id in seen:
            duplicates += 1
            logger.debug(f"Duplicate post {post.post_id} skipped")
            continue
        seen.add(post.post_id)
        unique.append(post)

    logger.info(
        f"Deduplication: {len(posts)} -> {len(unique)} posts "
        f"({duplicates} duplicates removed)"
    )
    return unique, duplicates
