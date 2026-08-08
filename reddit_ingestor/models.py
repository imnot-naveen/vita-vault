"""Domain models for Reddit content."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Comment:
    """A single Reddit comment."""

    comment_id: str
    post_id: str
    author: str
    body: str
    score: int
    created_utc: float


@dataclass(frozen=True)
class Post:
    """A single Reddit post with its comments."""

    post_id: str
    subreddit: str
    title: str
    selftext: str
    score: int
    author: str
    created_utc: float
    url: str
    flair: str | None
    comments: list[Comment] = field(default_factory=list)

    @property
    def num_comments(self) -> int:
        """Return the number of comments attached to this post."""
        return len(self.comments)


@dataclass
class ScrapeStats:
    """Accumulates pipeline statistics across subreddits."""

    posts_fetched: int = 0
    posts_skipped: int = 0
    comments_fetched: int = 0
    comments_kept: int = 0
    duplicates_removed: int = 0
    subreddits_processed: int = 0

    def merge(self, other: ScrapeStats) -> None:
        """Merge another stats object into this one."""
        self.posts_fetched += other.posts_fetched
        self.posts_skipped += other.posts_skipped
        self.comments_fetched += other.comments_fetched
        self.comments_kept += other.comments_kept
        self.duplicates_removed += other.duplicates_removed
        self.subreddits_processed += other.subreddits_processed
