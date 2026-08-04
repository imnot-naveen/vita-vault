"""SQLite storage writer for Reddit content."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from loguru import logger

from reddit_ingestor.models import Post


_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
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

CREATE TABLE IF NOT EXISTS comments (
    comment_id  TEXT PRIMARY KEY,
    post_id     TEXT NOT NULL,
    author      TEXT NOT NULL,
    body        TEXT NOT NULL,
    score       INTEGER NOT NULL,
    created_utc REAL NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(post_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
CREATE INDEX IF NOT EXISTS idx_posts_created   ON posts(created_utc);
CREATE INDEX IF NOT EXISTS idx_posts_post_id   ON posts(post_id);

CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_created ON comments(created_utc);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection and apply the schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    return conn


def write_sqlite(posts: list[Post], db_path: Path) -> dict[str, int]:
    """Write posts and their comments to a SQLite database.

    Duplicate ``post_id`` or ``comment_id`` values are silently ignored
    (``INSERT OR IGNORE``).

    Args:
        posts: Cleaned and deduplicated posts.
        db_path: Path to the ``.db`` file.

    Returns:
        A dict with ``posts_inserted`` and ``comments_inserted`` counts.
    """
    conn = _connect(db_path)
    cursor = conn.cursor()

    posts_inserted = 0
    comments_inserted = 0

    for post in posts:
        cursor.execute(
            "INSERT OR IGNORE INTO posts "
            "(post_id, subreddit, title, selftext, score, author, created_utc, url, flair) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                post.post_id,
                post.subreddit,
                post.title,
                post.selftext,
                post.score,
                post.author,
                post.created_utc,
                post.url,
                post.flair,
            ),
        )
        if cursor.rowcount > 0:
            posts_inserted += 1

        for comment in post.comments:
            cursor.execute(
                "INSERT OR IGNORE INTO comments "
                "(comment_id, post_id, author, body, score, created_utc) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    comment.comment_id,
                    comment.post_id,
                    comment.author,
                    comment.body,
                    comment.score,
                    comment.created_utc,
                ),
            )
            if cursor.rowcount > 0:
                comments_inserted += 1

    conn.commit()
    conn.close()

    logger.info(
        f"Wrote to SQLite: {posts_inserted} posts, "
        f"{comments_inserted} comments"
    )
    return {"posts_inserted": posts_inserted, "comments_inserted": comments_inserted}
