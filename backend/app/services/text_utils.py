"""Shared text normalization for keyword/pattern matching.

Plain `.lower()` substring matching misses accent variants that are common
and interchangeable in everyday Spanish (página/pagina, posición/posicion),
so every keyword/pattern check in the rules engine goes through
`normalize` first rather than comparing raw lowercased strings.
"""

import unicodedata


def normalize(text: str) -> str:
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_subreddit(name: str) -> str:
    """Canonical storage/comparison form of a subreddit name.

    Reddit's API returns the bare name ("SaaS"), but people naturally type
    the display form ("r/SaaS", "/r/saas", or a pasted URL fragment). The
    community watch-list is matched against the API's value, so a name
    stored with a prefix would silently never match and every post from that
    subreddit would be filtered out as `community_not_watched`.

    Casing is preserved (Reddit shows "SaaS", not "saas"); comparison is done
    via `subreddits_match` so the two concerns stay separate. This is the
    single place that knows how to strip the prefix — callers must not
    reimplement it.
    """
    if not name:
        return ""
    cleaned = name.strip().lstrip("/")
    lowered = cleaned.lower()
    if lowered.startswith("r/"):
        cleaned = cleaned[2:]
    return cleaned.strip().strip("/")


def subreddits_match(left: str, right: str) -> bool:
    """Case-insensitive comparison of two subreddit names in any input form."""
    return normalize_subreddit(left).lower() == normalize_subreddit(right).lower()
