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
