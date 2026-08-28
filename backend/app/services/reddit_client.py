"""Read-only adapter for the official Reddit Data API.

This module deliberately contains no HTML/browser scraping and no write
endpoints. Network calls are gated by REDDIT_API_ENABLED and are made only
with an OAuth bearer token.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("radarin.reddit")
REDDIT_OAUTH_BASE = "https://oauth.reddit.com"
REDDIT_WWW_BASE = "https://www.reddit.com"
READ_ONLY_SCOPES = ["identity", "read", "mysubreddits"]


class RedditIntegrationDisabled(RuntimeError):
    pass


class RedditAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, rate_limit: "RateLimitInfo | None" = None):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limit = rate_limit


@dataclass(frozen=True)
class RateLimitInfo:
    remaining: float | None = None
    used: float | None = None
    reset_seconds: float | None = None

    def as_dict(self) -> dict[str, float | None]:
        return {
            "rate_remaining": self.remaining,
            "rate_used": self.used,
            "rate_reset_seconds": self.reset_seconds,
        }


@dataclass
class RedditPost:
    id: str
    subreddit: str
    title: str
    selftext: str
    author: str
    url: str
    permalink: str
    created_utc: float
    num_comments: int
    score: int
    removed: bool


@dataclass
class RedditListingPage:
    posts: list[RedditPost]
    after: str | None
    rate_limit: RateLimitInfo


def _rate_limit_from_headers(headers: Any) -> RateLimitInfo:
    def number(name: str) -> float | None:
        raw = headers.get(name)
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    return RateLimitInfo(
        remaining=number("x-ratelimit-remaining"),
        used=number("x-ratelimit-used"),
        reset_seconds=number("x-ratelimit-reset"),
    )


def _require_enabled(settings: Settings) -> None:
    if not settings.reddit_api_enabled:
        raise RedditIntegrationDisabled("REDDIT_API_ENABLED is false")


def build_authorize_url(settings: Settings, state: str) -> str:
    _require_enabled(settings)
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        raise RedditAPIError("Reddit OAuth credentials are not configured")
    params = (
        f"client_id={settings.reddit_client_id}&response_type=code&state={state}"
        f"&redirect_uri={settings.reddit_redirect_uri}&duration=permanent"
        f"&scope={'+'.join(READ_ONLY_SCOPES)}"
    )
    return f"{REDDIT_WWW_BASE}/api/v1/authorize?{params}"


async def exchange_code_for_token(settings: Settings, code: str) -> dict:
    _require_enabled(settings)
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        raise RedditAPIError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required")
    async with httpx.AsyncClient(
        auth=(settings.reddit_client_id, settings.reddit_client_secret),
        headers={"User-Agent": settings.reddit_user_agent},
        timeout=15,
    ) as client:
        resp = await client.post(
            f"{REDDIT_WWW_BASE}/api/v1/access_token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.reddit_redirect_uri,
            },
        )
        if resp.status_code >= 400:
            raise RedditAPIError(
                f"Reddit OAuth token exchange failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
                rate_limit=_rate_limit_from_headers(resp.headers),
            )
        return resp.json()


async def _get_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    *,
    max_retries: int = 4,
) -> httpx.Response:
    delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            resp = await client.get(url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt >= max_retries:
                raise RedditAPIError(
                    f"Reddit request failed after {max_retries + 1} attempts: {type(exc).__name__}"
                ) from exc
            wait = min(delay, 60.0) + random.uniform(0, 0.5)
            logger.warning("reddit_request_retry reason=%s attempt=%s wait_seconds=%.2f", type(exc).__name__, attempt + 1, wait)
            await asyncio.sleep(wait)
            delay *= 2
            continue

        rate_limit = _rate_limit_from_headers(resp.headers)
        if resp.status_code == 429 or 500 <= resp.status_code <= 599:
            if attempt >= max_retries:
                raise RedditAPIError(
                    f"Reddit request failed after {max_retries + 1} attempts with HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    rate_limit=rate_limit,
                )
            retry_after = resp.headers.get("retry-after")
            try:
                requested_wait = float(retry_after) if retry_after is not None else delay
            except (TypeError, ValueError):
                requested_wait = delay
            wait = min(max(requested_wait, 0.0), 60.0) + random.uniform(0, 0.5)
            logger.warning(
                "reddit_request_retry status=%s attempt=%s wait_seconds=%.2f rate_remaining=%s rate_used=%s rate_reset=%s",
                resp.status_code, attempt + 1, wait, rate_limit.remaining, rate_limit.used, rate_limit.reset_seconds,
            )
            await asyncio.sleep(wait)
            delay *= 2
            continue

        if resp.status_code >= 400:
            raise RedditAPIError(
                f"Reddit request failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
                rate_limit=rate_limit,
            )
        return resp

    raise AssertionError("unreachable")


def _post_from_data(data: dict) -> RedditPost:
    permalink = data.get("permalink", "")
    selftext = data.get("selftext") or ""
    author = data.get("author") or ""
    removed = bool(data.get("removed_by_category")) or (
        not author and selftext in ("[removed]", "[deleted]")
    )
    return RedditPost(
        id=data.get("id", ""),
        subreddit=data.get("subreddit", ""),
        title=data.get("title", ""),
        selftext=selftext,
        author=author,
        url=f"https://reddit.com{permalink}" if permalink else "",
        permalink=permalink,
        created_utc=float(data.get("created_utc") or 0),
        num_comments=int(data.get("num_comments") or 0),
        score=int(data.get("score") or 0),
        removed=removed,
    )


async def fetch_new_posts_page(
    settings: Settings,
    access_token: str,
    subreddit: str,
    *,
    limit: int = 25,
    after: str | None = None,
    max_retries: int | None = None,
) -> RedditListingPage:
    _require_enabled(settings)
    if not access_token:
        raise RedditAPIError("A Reddit OAuth access token is required")
    params: dict[str, Any] = {"limit": min(max(limit, 1), 100), "raw_json": 1}
    if after:
        params["after"] = after
    async with httpx.AsyncClient(
        headers={
            "Authorization": f"bearer {access_token}",
            "User-Agent": settings.reddit_user_agent,
        },
        timeout=15,
    ) as client:
        resp = await _get_with_backoff(
            client,
            f"{REDDIT_OAUTH_BASE}/r/{subreddit}/new",
            params,
            max_retries=settings.reddit_max_retries if max_retries is None else max_retries,
        )
        payload = resp.json()
    listing = payload.get("data", {})
    return RedditListingPage(
        posts=[_post_from_data(child.get("data", {})) for child in listing.get("children", [])],
        after=listing.get("after"),
        rate_limit=_rate_limit_from_headers(resp.headers),
    )


async def fetch_new_posts(
    settings: Settings,
    access_token: str,
    subreddit: str,
    limit: int = 25,
) -> list[RedditPost]:
    """Backwards-compatible list API for callers that do not need cursors."""
    page = await fetch_new_posts_page(settings, access_token, subreddit, limit=limit)
    return page.posts


async def fetch_posts_by_ids(
    settings: Settings,
    access_token: str,
    post_ids: list[str],
    *,
    max_retries: int | None = None,
) -> tuple[dict[str, RedditPost], RateLimitInfo]:
    """Read-only recheck through the documented /api/info listing endpoint.

    Missing children are intentionally not treated as deletion: an API response
    may be partial or temporarily unavailable. Only explicit removed markers
    are actionable to the deletion-sync job.
    """
    _require_enabled(settings)
    if not access_token:
        raise RedditAPIError("A Reddit OAuth access token is required")
    if not post_ids:
        return {}, RateLimitInfo()
    ids = ",".join(f"t3_{post_id}" for post_id in post_ids)
    async with httpx.AsyncClient(
        headers={
            "Authorization": f"bearer {access_token}",
            "User-Agent": settings.reddit_user_agent,
        },
        timeout=15,
    ) as client:
        resp = await _get_with_backoff(
            client,
            f"{REDDIT_OAUTH_BASE}/api/info",
            {"id": ids, "raw_json": 1},
            max_retries=settings.reddit_max_retries if max_retries is None else max_retries,
        )
        payload = resp.json()
    posts = {
        post.id: post
        for child in payload.get("data", {}).get("children", [])
        if (post := _post_from_data(child.get("data", {}))).id
    }
    return posts, _rate_limit_from_headers(resp.headers)
