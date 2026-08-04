"""JSON storage writer for Reddit content."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from reddit_ingestor.models import Comment, Post


def _comment_to_dict(comment: Comment) -> dict[str, Any]:
    """Serialize a ``Comment`` to a plain dictionary."""
    return {
        "comment_id": comment.comment_id,
        "post_id": comment.post_id,
        "author": comment.author,
        "body": comment.body,
        "score": comment.score,
        "created_utc": comment.created_utc,
    }


def _post_to_dict(post: Post) -> dict[str, Any]:
    """Serialize a ``Post`` to a plain dictionary."""
    return {
        "post_id": post.post_id,
        "subreddit": post.subreddit,
        "title": post.title,
        "selftext": post.selftext,
        "score": post.score,
        "author": post.author,
        "created_utc": post.created_utc,
        "url": post.url,
        "flair": post.flair,
        "num_comments": post.num_comments,
        "comments": [_comment_to_dict(c) for c in post.comments],
    }


def write_json(posts: list[Post], output_path: Path) -> dict[str, Any]:
    """Write posts to a JSON file.

    Args:
        posts: Cleaned and deduplicated posts.
        output_path: Destination file path.

    Returns:
        A dict with ``file_size_mb`` and ``post_count``.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = [_post_to_dict(p) for p in posts]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"Wrote {len(posts)} posts to {output_path} ({size_mb:.2f} MB)")

    return {"file_size_mb": round(size_mb, 2), "post_count": len(posts)}
