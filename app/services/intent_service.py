"""Intent loading and keyword-based matching helpers."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List

INTENT_PATH = Path("data/intent_seed.csv")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "why",
    "you",
}


def load_intents(path: Path = INTENT_PATH) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _stem_token(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            return token[: -len(suffix)]
    return token


def _stem_set(text: str) -> set[str]:
    return {_stem_token(token) for token in text.split(" ") if token}


def _keyword_hits(message: str, keyword_blob: str) -> int:
    keywords = [_normalize_text(k.strip()) for k in keyword_blob.split(",") if k.strip()]
    if not keywords:
        return 0
    hits = 0
    msg_tokens = set(message.split(" "))
    msg_stems = _stem_set(message)

    for kw in keywords:
        if kw in message:
            hits += 2
            continue
        kw_tokens = [token for token in kw.split(" ") if token]
        kw_stems = {_stem_token(token) for token in kw_tokens}
        if kw_tokens and (all(token in msg_tokens for token in kw_tokens) or kw_stems.issubset(msg_stems)):
            hits += 1
    return hits


def _sample_hits(message: str, sample: str) -> int:
    sample = _normalize_text(sample)
    if not sample:
        return 0
    sample_tokens = [
        token
        for token in sample.split(" ")
        if len(token) > 2 and token not in STOPWORDS
    ]
    if not sample_tokens:
        return 0
    msg_tokens = set(message.split(" "))
    msg_stems = _stem_set(message)
    return sum(1 for token in sample_tokens if token in msg_tokens or _stem_token(token) in msg_stems)


def match_intent(message: str, intents: List[Dict[str, str]]) -> Dict[str, str] | None:
    msg = _normalize_text(message)
    best_row = None
    best_score = 0

    for row in intents:
        if row.get("is_active", "").lower() != "true":
            continue

        kw_hits = _keyword_hits(msg, row.get("keywords", ""))
        sample_hits = _sample_hits(msg, row.get("sample_utterance", ""))
        if kw_hits == 0 and sample_hits == 0:
            continue

        priority_bonus = max(0, 4 - int(row.get("priority", "3")))
        score = kw_hits * 3 + sample_hits * 2 + priority_bonus

        # Avoid over-matching weak lexical overlap.
        if kw_hits == 0 and sample_hits < 2:
            continue

        if score > best_score:
            best_score = score
            best_row = row

    return best_row if best_score > 0 else None
