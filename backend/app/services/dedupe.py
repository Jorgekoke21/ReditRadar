"""Deduplication helpers.

A conversation is considered a duplicate of an existing one for the same
account when any of these match:
  1. reddit_post_id (exact ID from Reddit)
  2. normalized URL
  3. hash of subreddit + normalized title + published date (catches manual
     re-entry of the same post without its Reddit ID/URL)

normalize_url and dedupe_hash are pure functions so scoring/import code and
tests can call them without touching the DB, keeping the import pipeline
idempotent: importing the same conversation twice never creates two rows.
"""

import hashlib
import re
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

from app.services.text_utils import normalize as normalize_accents


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    netloc = parts.netloc.lower().replace("www.", "")
    # Reddit URLs carry a slug after the post id; keep scheme+host+path only.
    return urlunsplit((parts.scheme or "https", netloc, path, "", ""))


def normalize_title(title: str) -> str:
    if not title:
        return ""
    # Accent-folded so "Cómo consigo clientes" and "Como consigo clientes"
    # hash identically — the same post retyped without accents is still a duplicate.
    folded = normalize_accents(title.strip())
    folded = re.sub(r"\s+", " ", folded)
    folded = re.sub(r"[^\w\s]", "", folded)
    return folded


def compute_dedupe_hash(
    subreddit: str, title: str, published: date | datetime | None, reddit_post_id: str | None = None
) -> str:
    day = ""
    if isinstance(published, datetime):
        day = published.date().isoformat()
    elif isinstance(published, date):
        day = published.isoformat()
    raw = f"{(subreddit or '').strip().lower()}|{normalize_title(title)}|{day}"
    # A real Reddit post id is the strongest identity signal available — fold
    # it in whenever we have one so two distinct posts that merely share a
    # subreddit, title and calendar day (a real possibility in an active
    # subreddit with a generic title) don't collide under this hash, which
    # `uq_conversation_account_dedupe_hash` enforces as unique per account.
    # Without an id (manual entry with no URL either), keep the coarser
    # content-only signature so re-pasting the same post text still dedupes —
    # that is this hash's actual job per the module docstring above.
    if reddit_post_id:
        raw = f"{raw}|{reddit_post_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
