"""Data cleaning processor for Reddit content."""

from __future__ import annotations

from loguru import logger

from reddit_ingestor.config import MIN_COMMENT_LENGTH
from reddit_ingestor.models import Comment, Post


def clean_comment(comment: Comment) -> bool:
    """Return True if the comment should be kept.

    Filters out deleted, removed, AutoModerator, and overly short comments.
    """
    if comment.author.lower() == "automoderator":
        return False
    if comment.body in ("[deleted]", "[removed]"):
        return False
    if len(comment.body.strip()) < MIN_COMMENT_LENGTH:
        return False
    return True


def clean_post(post: Post) -> Post:
    """Clean a post and its comments.

    Removes invalid comments and returns a new ``Post`` with only
    the comments that pass all filters.
    """
    original_count = len(post.comments)
    kept = [c for c in post.comments if clean_comment(c)]
    removed = original_count - len(kept)
    if removed:
        logger.debug(
            f"Post {post.post_id}: removed {removed} comments "
            f"({original_count} -> {len(kept)})"
        )
    return Post(
        post_id=post.post_id,
        subreddit=post.subreddit,
        title=post.title,
        selftext=post.selftext,
        score=post.score,
        author=post.author,
        created_utc=post.created_utc,
        url=post.url,
        flair=post.flair,
        comments=kept,
    )


def clean_posts(posts: list[Post]) -> list[Post]:
    """Clean a batch of posts.

    Args:
        posts: Raw posts straight from the scraper.

    Returns:
        Cleaned posts with filtered comments.
    """
    logger.info(f"Cleaning {len(posts)} posts")
    cleaned = [clean_post(p) for p in posts]
    total_comments_before = sum(len(p.comments) for p in posts)
    total_comments_after = sum(len(p.comments) for p in cleaned)
    logger.info(
        f"Cleaning done: {total_comments_before} -> {total_comments_after} comments"
    )
    return cleaned
