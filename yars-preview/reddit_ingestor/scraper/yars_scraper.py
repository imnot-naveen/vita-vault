"""YARS-based Reddit scraper implementation."""

from __future__ import annotations

import random
import time
from typing import Any

from loguru import logger

from reddit_ingestor.config import (
    BACKOFF_BASE,
    BACKOFF_MAX_SECONDS,
    HTTP_429_PAUSE_SECONDS,
    MAX_DELAY_SECONDS,
    MAX_RETRIES,
    MIN_COMMENT_LENGTH,
    MIN_DELAY_SECONDS,
    PROXY_URL,
)
from reddit_ingestor.models import Comment, Post
from reddit_ingestor.scraper.base import BaseScraper


class YARSScraper(BaseScraper):
    """Scraper backed by the YARS library (datavorous/yars).

    YARS already has internal retry logic via urllib3. We layer
    additional rate-limiting and retry on top for the pipeline.
    """

    def __init__(self) -> None:
        """Initialise the YARS client with optional proxy."""
        from yars.yars import YARS

        self._yars = YARS(proxy=PROXY_URL)
        if PROXY_URL:
            logger.info(f"YARS using proxy: {PROXY_URL}")

    # ── Rate limiting helpers ────────────────────────────────────────

    @staticmethod
    def _random_delay() -> None:
        """Sleep for a random duration between requests."""
        delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        logger.debug(f"Sleeping {delay:.2f}s")
        time.sleep(delay)

    @staticmethod
    def _exponential_backoff(attempt: int) -> None:
        """Sleep with exponential back-off based on retry attempt number."""
        wait = min(BACKOFF_BASE**attempt, BACKOFF_MAX_SECONDS)
        logger.debug(f"Backoff attempt {attempt}: sleeping {wait:.2f}s")
        time.sleep(wait)

    @staticmethod
    def _handle_429() -> None:
        """Pause when a 429 (rate-limit) response is detected."""
        logger.warning(
            f"HTTP 429 detected — pausing for {HTTP_429_PAUSE_SECONDS:.0f}s"
        )
        time.sleep(HTTP_429_PAUSE_SECONDS)

    # ── Retry wrapper ───────────────────────────────────────────────

    def _with_retry(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* with retries, back-off, and 429 handling.

        Args:
            fn: Callable to invoke.
            *args: Positional arguments forwarded to *fn*.
            **kwargs: Keyword arguments forwarded to *fn*.

        Returns:
            The return value of *fn*.

        Raises:
            The last exception if all retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                exc_str = str(exc).lower()
                if "429" in exc_str or "rate" in exc_str:
                    self._handle_429()
                else:
                    logger.warning(
                        f"Attempt {attempt}/{MAX_RETRIES} failed: {exc}"
                    )
                if attempt < MAX_RETRIES:
                    self._exponential_backoff(attempt)
        raise last_exc  # type: ignore[misc]

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _is_valid_post(raw: dict[str, Any]) -> bool:
        """Return True if the raw post dict should be kept."""
        # YARS returns dicts; deleted posts have [deleted] selftext
        selftext = raw.get("description", "") or ""
        if selftext in ("[deleted]", "[removed]"):
            return False
        return True

    @staticmethod
    def _is_valid_comment(comment: dict[str, Any]) -> bool:
        """Return True if the raw comment dict should be kept."""
        author = comment.get("author", "")
        body = comment.get("body", "")
        if not author or author == "[deleted]":
            return False
        if author.lower() == "automoderator":
            return False
        if body in ("[deleted]", "[removed]"):
            return False
        if len(body.strip()) < MIN_COMMENT_LENGTH:
            return False
        return True

    def _parse_post_id(self, permalink: str) -> str:
        """Extract the post ID from a Reddit permalink."""
        # permalink like: /r/subreddit/comments/abc123/title_slug/
        parts = permalink.strip("/").split("/")
        if "comments" in parts:
            idx = parts.index("comments")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return permalink

    def _build_comments(
        self, raw_comments: list[dict[str, Any]], post_id: str
    ) -> list[Comment]:
        """Convert raw YARS comment dicts into domain ``Comment`` objects."""
        seen: set[str] = set()
        comments: list[Comment] = []

        for raw in raw_comments:
            # Recurse into replies
            replies = raw.get("replies", [])
            if replies:
                comments.extend(self._build_comments(replies, post_id))

            if not self._is_valid_comment(raw):
                continue

            body = raw["body"].strip()
            if body in seen:
                continue
            seen.add(body)

            comments.append(
                Comment(
                    comment_id=f"{post_id}_{hash(body) & 0xFFFFFFFF:08x}",
                    post_id=post_id,
                    author=raw["author"],
                    body=body,
                    score=int(raw.get("score", 0)),
                    created_utc=0.0,  # YARS doesn't expose this in comments
                )
            )

        return comments

    # ── Public interface ─────────────────────────────────────────────

    def fetch_subreddit_posts(self, subreddit: str, limit: int) -> list[Post]:
        """Fetch the newest posts from *subreddit*.

        Comments are **not** hydrated here — call ``fetch_post`` separately.
        """
        logger.info(f"Fetching {limit} newest posts from r/{subreddit}")

        def _do() -> list[Post]:
            raw_posts = self._yars.fetch_subreddit_posts(
                subreddit, limit=limit, category="new"
            )
            result: list[Post] = []
            for raw in raw_posts:
                if not self._is_valid_post(raw):
                    logger.debug(f"Skipping invalid post: {raw.get('title', '?')}")
                    continue
                permalink = raw.get("permalink", "")
                post_id = self._parse_post_id(permalink)
                post = Post(
                    post_id=post_id,
                    subreddit=subreddit,
                    title=raw.get("title", ""),
                    selftext=raw.get("description", "") or "",
                    score=int(raw.get("score", 0)),
                    author=raw.get("author", "[deleted]"),
                    created_utc=float(raw.get("created_utc", 0.0)),
                    url=f"https://reddit.com{permalink}",
                    flair=None,
                    comments=[],
                )
                result.append(post)
            return result

        try:
            posts = self._with_retry(_do)
            logger.info(f"Fetched {len(posts)} valid posts from r/{subreddit}")
            return posts
        except Exception as exc:
            logger.error(f"Failed to fetch posts from r/{subreddit}: {exc}")
            return []

    def fetch_post(self, post_id: str) -> Post | None:
        """Fetch a single post by its permalink path with comments.

        Args:
            post_id: The Reddit post ID (used to reconstruct permalink).

        Returns:
            A hydrated ``Post`` or ``None`` on failure.
        """
        logger.debug(f"Fetching post {post_id}")

        def _do() -> Post | None:
            # YARS scrape_post_details expects a permalink path
            permalink = f"/comments/{post_id}"
            details = self._yars.scrape_post_details(permalink)
            if details is None:
                return None

            raw_comments = details.get("comments", [])
            comments = self._build_comments(raw_comments, post_id)
            comments.sort(key=lambda c: c.score, reverse=True)

            return Post(
                post_id=post_id,
                subreddit="",
                title=details.get("title", ""),
                selftext=details.get("body", ""),
                score=0,
                author="[unknown]",
                created_utc=0.0,
                url=f"https://reddit.com/comments/{post_id}",
                flair=None,
                comments=comments,
            )

        try:
            post = self._with_retry(_do)
            if post is not None:
                logger.debug(
                    f"Post {post_id}: {len(post.comments)} comments"
                )
            return post
        except Exception as exc:
            logger.warning(f"Failed to fetch post {post_id}: {exc}")
            return None

    def fetch_comments(self, post_id: str, limit: int) -> list[Comment]:
        """Fetch up to *limit* comments for the given post."""
        post = self.fetch_post(post_id)
        if post is None:
            return []
        return post.comments[:limit]
