"""Abstract scraper interface for Reddit content."""

from __future__ import annotations

from abc import ABC, abstractmethod

from reddit_ingestor.models import Comment, Post


class BaseScraper(ABC):
    """Abstract base class that every scraper implementation must satisfy.

    Implementations fetch raw data from Reddit. The pipeline never imports
    a concrete scraper directly; it programs against this interface.
    """

    @abstractmethod
    def fetch_subreddit_posts(self, subreddit: str, limit: int) -> list[Post]:
        """Fetch the newest posts from a subreddit.

        Args:
            subreddit: Name of the subreddit (without the ``r/`` prefix).
            limit: Maximum number of posts to retrieve.

        Returns:
            A list of ``Post`` objects. Comments may be empty at this stage;
            the pipeline can call ``fetch_comments`` to hydrate them.
        """
        ...

    @abstractmethod
    def fetch_post(self, post_id: str) -> Post | None:
        """Fetch a single post by its ID.

        Args:
            post_id: The Reddit post ID (e.g. ``"abc123"``).

        Returns:
            A ``Post`` object, or ``None`` if the post could not be retrieved.
        """
        ...

    @abstractmethod
    def fetch_comments(self, post_id: str, limit: int) -> list[Comment]:
        """Fetch comments for a given post.

        Args:
            post_id: The Reddit post ID.
            limit: Maximum number of comments to retrieve.

        Returns:
            A list of ``Comment`` objects.
        """
        ...
