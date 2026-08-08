"""PRAW-based Reddit scraper using OAuth2 API.

This is the recommended scraper for production use. It uses Reddit's
official OAuth2 API which works from any IP (no proxy needed).

Setup:
  1. Go to https://www.reddit.com/prefs/apps
  2. Create a "script" type app
  3. Set environment variables:
       REDDIT_CLIENT_ID=<your client id>
       REDDIT_CLIENT_SECRET=<your client secret>
       REDDIT_USERNAME=<your reddit username>
       REDDIT_PASSWORD=<your reddit password>
"""

from __future__ import annotations

import random
import time
from typing import Any

from loguru import logger

from reddit_ingestor.config import (
    BACKOFF_BASE,
    BACKOFF_MAX_SECONDS,
    HTTP_429_PAUSE_SECONDS,
    MAX_COMMENTS,
    MAX_DELAY_SECONDS,
    MAX_RETRIES,
    MIN_COMMENT_LENGTH,
    MIN_DELAY_SECONDS,
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_PASSWORD,
    REDDIT_USER_AGENT,
    REDDIT_USERNAME,
)
from reddit_ingestor.models import Comment, Post
from reddit_ingestor.scraper.base import BaseScraper


class PRAWScraper(BaseScraper):
    """Scraper using PRAW (Python Reddit API Wrapper) with OAuth2.

    Works from any IP including datacenter/cloud servers.
    Requires Reddit API credentials (see module docstring).
    """

    def __init__(self) -> None:
        """Initialise the PRAW Reddit client."""
        import praw

        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            raise ValueError(
                "PRAW scraper requires Reddit API credentials. "
                "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET "
                "environment variables. "
                "Create an app at https://www.reddit.com/prefs/apps"
            )

        self._reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=REDDIT_USER_AGENT,
        )
        logger.info("PRAW scraper initialised with OAuth2")

    # ── Rate limiting ────────────────────────────────────────────────

    @staticmethod
    def _random_delay() -> None:
        """Sleep for a random duration between requests."""
        delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        logger.debug(f"Rate-limit sleep: {delay:.2f}s")
        time.sleep(delay)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _convert_post(submission: Any, comments: list[Comment]) -> Post:
        """Convert a PRAW submission to our domain Post."""
        return Post(
            post_id=str(submission.id),
            subreddit=str(submission.subreddit),
            title=str(submission.title),
            selftext=str(getattr(submission, "selftext", "")),
            score=int(getattr(submission, "score", 0)),
            author=str(getattr(submission, "author", "[deleted]")),
            created_utc=float(getattr(submission, "created_utc", 0.0)),
            url=f"https://reddit.com{submission.permalink}",
            flair=getattr(submission, "link_flair_text", None),
            comments=comments,
        )

    def _extract_comments(self, submission: Any, post_id: str) -> list[Comment]:
        """Extract, filter, and sort comments from a PRAW submission."""
        try:
            submission.comments.replace_more(limit=0)
        except Exception as exc:
            logger.warning(f"replace_more failed for {post_id}: {exc}")

        seen: set[str] = set()
        comments: list[Comment] = []

        for c in submission.comments.list():
            if not hasattr(c, "body"):
                continue
            author = str(c.author) if c.author else ""
            body = c.body.strip()

            if (
                not author
                or author == "[deleted]"
                or author.lower() == "automoderator"
                or body in ("[deleted]", "[removed]")
                or len(body) < MIN_COMMENT_LENGTH
            ):
                continue

            if body in seen:
                continue
            seen.add(body)

            comments.append(
                Comment(
                    comment_id=str(c.id),
                    post_id=post_id,
                    author=author,
                    body=body,
                    score=int(getattr(c, "score", 0)),
                    created_utc=float(getattr(c, "created_utc", 0.0)),
                )
            )

        comments.sort(key=lambda c: c.score, reverse=True)
        return comments

    # ── Public interface ─────────────────────────────────────────────

    def fetch_subreddit_posts(self, subreddit: str, limit: int) -> list[Post]:
        """Fetch the newest posts from a subreddit.

        Comments are **not** hydrated here — call ``fetch_post`` separately.
        """
        logger.info(f"Fetching {limit} newest posts from r/{subreddit}")

        try:
            sub = self._reddit.subreddit(subreddit)
            posts: list[Post] = []
            for submission in sub.new(limit=limit):
                if getattr(submission, "selftext", "") in ("[deleted]", "[removed]"):
                    continue
                posts.append(self._convert_post(submission, comments=[]))
                self._random_delay()

            logger.info(f"Fetched {len(posts)} posts from r/{subreddit}")
            return posts

        except Exception as exc:
            logger.error(f"Failed to fetch posts from r/{subreddit}: {exc}")
            return []

    def fetch_post(self, post_id: str) -> Post | None:
        """Fetch a single post with all comments hydrated."""
        logger.debug(f"Fetching post {post_id}")

        try:
            submission = self._reddit.submission(id=post_id)
            comments = self._extract_comments(submission, post_id)
            post = self._convert_post(submission, comments)
            logger.debug(f"Post {post_id}: {len(comments)} comments")
            return post

        except Exception as exc:
            logger.warning(f"Failed to fetch post {post_id}: {exc}")
            return None

    def fetch_comments(self, post_id: str, limit: int) -> list[Comment]:
        """Fetch up to *limit* comments for a post."""
        post = self.fetch_post(post_id)
        if post is None:
            return []
        return post.comments[:limit]
