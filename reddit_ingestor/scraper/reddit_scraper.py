"""Direct Reddit JSON API scraper using requests.

This scraper talks to Reddit's public .json endpoints via old.reddit.com,
which is less aggressive about blocking datacenter IPs than www.reddit.com.
It uses a session with cookies and conservative rate limiting.
"""

from __future__ import annotations

import random
import time
from typing import Any

import requests
from loguru import logger

from reddit_ingestor.config import (
    HTTP_429_PAUSE_SECONDS,
    MAX_DELAY_SECONDS,
    MAX_RETRIES,
    MIN_COMMENT_LENGTH,
    MIN_DELAY_SECONDS,
    PROXY_URL,
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from reddit_ingestor.models import Comment, Post
from reddit_ingestor.scraper.base import BaseScraper

REDDIT_BASE = "https://old.reddit.com"


class RedditJSONScraper(BaseScraper):
    """Scraper that hits Reddit's old.reddit.com .json endpoints.

    Uses a persistent session with cookies. Only retries on 429,
    never on 403 (which means permanent block, not transient).
    """

    def __init__(self) -> None:
        """Build a requests session and warm it with a homepage visit."""
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })

        if PROXY_URL:
            self._session.proxies.update({
                "http": PROXY_URL,
                "https": PROXY_URL,
            })
            logger.info(f"Using proxy: {PROXY_URL}")

        # Warm the session by visiting the homepage (gets cookies)
        self._warm_session()

    def _warm_session(self) -> None:
        """Visit the homepage to acquire session cookies."""
        try:
            resp = self._session.get(REDDIT_BASE, timeout=REQUEST_TIMEOUT)
            logger.debug(f"Session warm: {resp.status_code}, cookies: {len(resp.cookies)}")
        except Exception as exc:
            logger.warning(f"Session warm failed: {exc}")

    # ── Rate limiting ────────────────────────────────────────────────

    @staticmethod
    def _random_delay() -> None:
        """Sleep for a random duration between requests."""
        delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        logger.debug(f"Rate-limit sleep: {delay:.2f}s")
        time.sleep(delay)

    @staticmethod
    def _handle_429() -> None:
        """Long pause when rate-limited."""
        logger.warning(f"HTTP 429 — pausing {HTTP_429_PAUSE_SECONDS:.0f}s")
        time.sleep(HTTP_429_PAUSE_SECONDS)

    # ── HTTP helper ──────────────────────────────────────────────────

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET a Reddit .json endpoint.

        Only retries on 429 (rate limit). 403 means permanent block
        and is not retried.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 429:
                    self._handle_429()
                    if attempt < MAX_RETRIES:
                        time.sleep(random.uniform(5, 15))
                    continue

                if resp.status_code == 403:
                    raise PermissionError(
                        f"Reddit blocked this request (403). "
                        f"Try running from a residential IP or use --scraper praw."
                    )

                resp.raise_for_status()
                return resp.json()

            except PermissionError:
                raise
            except Exception as exc:
                logger.warning(
                    f"Attempt {attempt}/{MAX_RETRIES} failed for {url}: {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(random.uniform(3, 8))

        raise RuntimeError(f"Failed after {MAX_RETRIES} attempts: {url}")

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_post_id(permalink: str) -> str:
        """Extract the post ID from a Reddit permalink."""
        parts = permalink.strip("/").split("/")
        if "comments" in parts:
            idx = parts.index("comments")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return permalink.split("/")[-1]

    def _collect_comments(
        self, children: list[dict[str, Any]], post_id: str
    ) -> list[Comment]:
        """Recursively collect comments from Reddit JSON children."""
        comments: list[Comment] = []
        for child in children:
            kind = child.get("kind")
            data = child.get("data", {})
            if kind == "t1":
                author = data.get("author", "")
                body = data.get("body", "").strip()
                if (
                    author
                    and author != "[deleted]"
                    and author.lower() != "automoderator"
                    and body not in ("[deleted]", "[removed]")
                    and len(body) >= MIN_COMMENT_LENGTH
                ):
                    comments.append(
                        Comment(
                            comment_id=data.get("id", ""),
                            post_id=post_id,
                            author=author,
                            body=body,
                            score=int(data.get("score", 0)),
                            created_utc=float(data.get("created_utc", 0.0)),
                        )
                    )
                replies = data.get("replies", "")
                if isinstance(replies, dict):
                    reply_children = replies.get("data", {}).get("children", [])
                    comments.extend(
                        self._collect_comments(reply_children, post_id)
                    )
        return comments

    # ── Public interface ─────────────────────────────────────────────

    def fetch_subreddit_posts(self, subreddit: str, limit: int) -> list[Post]:
        """Fetch the newest posts from a subreddit.

        Comments are **not** hydrated here.
        """
        logger.info(f"Fetching {limit} newest posts from r/{subreddit}")
        url = f"{REDDIT_BASE}/r/{subreddit}/new.json"
        params: dict[str, Any] = {"limit": min(limit, 100)}

        posts: list[Post] = []
        after: str | None = None
        fetched = 0

        try:
            while fetched < limit:
                page_params = dict(params)
                if after:
                    page_params["after"] = after

                data = self._get_json(url, page_params)
                children = data.get("data", {}).get("children", [])
                if not children:
                    break

                for child in children:
                    d = child.get("data", {})
                    selftext = d.get("selftext", "") or ""
                    if selftext in ("[deleted]", "[removed]"):
                        continue

                    permalink = d.get("permalink", "")
                    posts.append(
                        Post(
                            post_id=self._parse_post_id(permalink),
                            subreddit=subreddit,
                            title=d.get("title", ""),
                            selftext=selftext,
                            score=int(d.get("score", 0)),
                            author=d.get("author", "[deleted]"),
                            created_utc=float(d.get("created_utc", 0.0)),
                            url=f"{REDDIT_BASE}{permalink}",
                            flair=d.get("link_flair_text"),
                            comments=[],
                        )
                    )
                    fetched += 1
                    if fetched >= limit:
                        break

                after = data.get("data", {}).get("after")
                if not after:
                    break
                self._random_delay()

            logger.info(f"Fetched {len(posts)} posts from r/{subreddit}")
            return posts

        except Exception as exc:
            logger.error(f"Failed to fetch posts from r/{subreddit}: {exc}")
            return []

    def fetch_post(self, post_id: str) -> Post | None:
        """Fetch a single post with all comments hydrated."""
        logger.debug(f"Fetching post {post_id}")
        url = f"{REDDIT_BASE}/comments/{post_id}.json"

        try:
            data = self._get_json(url)
            if not isinstance(data, list) or len(data) < 2:
                logger.warning(f"Unexpected response for {post_id}")
                return None

            post_data = data[0]["data"]["children"][0]["data"]
            comment_children = data[1]["data"]["children"]

            comments = self._collect_comments(comment_children, post_id)
            comments.sort(key=lambda c: c.score, reverse=True)

            return Post(
                post_id=post_id,
                subreddit=post_data.get("subreddit", ""),
                title=post_data.get("title", ""),
                selftext=post_data.get("selftext", ""),
                score=int(post_data.get("score", 0)),
                author=post_data.get("author", "[deleted]"),
                created_utc=float(post_data.get("created_utc", 0.0)),
                url=f"{REDDIT_BASE}{post_data.get('permalink', '')}",
                flair=post_data.get("link_flair_text"),
                comments=comments,
            )

        except Exception as exc:
            logger.warning(f"Failed to fetch post {post_id}: {exc}")
            return None

    def fetch_comments(self, post_id: str, limit: int) -> list[Comment]:
        """Fetch up to *limit* comments for a post."""
        post = self.fetch_post(post_id)
        if post is None:
            return []
        return post.comments[:limit]
