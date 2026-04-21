"""AI FAQ service with strict SQL-first answering strategy."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from services.event_service import search_upcoming_events
from services.faq_service import load_faq
from services.item_service import search_active_items

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "could",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "list",
    "me",
    "my",
    "of",
    "on",
    "please",
    "show",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
    "you",
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _normalize(text)) if len(t) > 1]


def _meaningful_tokens(text: str) -> List[str]:
    return [t for t in _tokens(text) if t not in STOPWORDS and len(t) > 2]


def _faq_rank(question: str, limit: int = 8) -> List[Tuple[int, Dict[str, str]]]:
    q_tokens = _meaningful_tokens(question)
    rows: List[Tuple[int, Dict[str, str]]] = []
    for row in load_faq():
        if row.get("is_active", "").lower() != "true":
            continue
        blob = f"{row.get('question','')} {row.get('keywords','')} {row.get('category','')}".lower()
        score = 0
        for token in q_tokens:
            if token in blob:
                score += 1
        if score > 0:
            rows.append((score, row))
    rows.sort(key=lambda x: (x[0], -int(x[1].get("priority", "3"))), reverse=True)
    return rows[:limit]


def _is_payment_query(question: str) -> bool:
    q = _normalize(question)
    keys = ["payment", "pay", "paypal", "alipay", "wechat", "card", "visa", "mastercard", "支付"]
    return any(k in q for k in keys)


def _is_item_query(question: str) -> bool:
    q = _normalize(question)
    keys = [
        "item",
        "items",
        "find",
        "looking",
        "category",
        "book",
        "books",
        "ipad",
        "laptop",
        "electronics",
        "furniture",
        "clothing",
        "home",
        "sports",
        "buy",
        "sell",
        "商品",
        "二手",
        "找",
    ]
    return any(k in q for k in keys)


def _is_event_query(question: str) -> bool:
    q = _normalize(question)
    keys = ["event", "events", "date", "when", "market", "exchange", "活动", "日期", "时间", "市集"]
    return any(k in q for k in keys)


def _format_items(items: List[Dict], limit: int = 10) -> str:
    if not items:
        return "No matching active items found."
    lines = [f"Found {min(len(items), limit)} matching active items:"]
    for item in items[:limit]:
        lines.append(
            f"- #{item['id']} {item['title']} | {item['category']} | HKD {item['price']} | {item['condition_level']}"
        )
    return "\n".join(lines)


def _format_events(events: List[Dict], limit: int = 10) -> str:
    if not events:
        return "No matching upcoming events found."
    lines = [f"Found {min(len(events), limit)} upcoming events:"]
    for event in events[:limit]:
        lines.append(
            f"- #{event['id']} {event['title']} | {event['event_type']} | {event['starts_at']} | {event['location']}"
        )
    return "\n".join(lines)


def _search_items_sql_first(question: str) -> List[Dict]:
    # 1) direct full-text style attempt
    rows = search_active_items(question, limit=20)
    if rows:
        return rows

    # 2) token-based query expansion
    merged: Dict[int, Dict] = {}
    for token in _meaningful_tokens(question):
        token_rows = search_active_items(token, limit=20)
        for row in token_rows:
            merged[int(row["id"])] = row
    if merged:
        return list(merged.values())

    # 3) broad listing fallback for item-oriented question
    return search_active_items(None, limit=20)


def _search_events_sql_first(question: str) -> List[Dict]:
    rows = search_upcoming_events(question, limit=20)
    if rows:
        return rows

    merged: Dict[int, Dict] = {}
    for token in _meaningful_tokens(question):
        token_rows = search_upcoming_events(token, limit=20)
        for row in token_rows:
            merged[int(row["id"])] = row
    if merged:
        return list(merged.values())

    return search_upcoming_events(None, limit=20)


def _sql_first_answer(question: str) -> Dict[str, str | int | None] | None:
    ranked_faq = _faq_rank(question, limit=8)
    top_faq = ranked_faq[0][1] if ranked_faq else None
    top_score = ranked_faq[0][0] if ranked_faq else 0

    # 1) Payment questions should be answered directly from FAQ.
    if _is_payment_query(question):
        payment_rows = [
            row
            for _, row in ranked_faq
            if row.get("category", "").lower() == "payment"
            or "payment" in row.get("keywords", "").lower()
            or "paypal" in row.get("keywords", "").lower()
        ]
        if payment_rows:
            row = payment_rows[0]
            return {
                "text": row["answer"],
                "latency_ms": 0,
                "model": None,
                "mode": "sql_faq_payment",
            }

    # 2) Item queries return direct SQL list.
    if _is_item_query(question):
        items = _search_items_sql_first(question)
        if items:
            return {
                "text": _format_items(items, limit=10),
                "latency_ms": 0,
                "model": None,
                "mode": "sql_items",
            }

    # 3) Event queries return direct SQL list with explicit dates.
    if _is_event_query(question):
        events = _search_events_sql_first(question)
        if events:
            return {
                "text": _format_events(events, limit=10),
                "latency_ms": 0,
                "model": None,
                "mode": "sql_events",
            }

    # 4) Generic FAQ direct answer if lexical confidence is high enough.
    if top_faq and top_score >= 2:
        return {
            "text": top_faq["answer"],
            "latency_ms": 0,
            "model": None,
            "mode": "sql_faq",
        }

    return None


def _faq_context_block(question: str) -> str:
    ranked = _faq_rank(question, limit=6)
    if not ranked:
        return "No direct FAQ rows matched."
    lines = []
    for score, row in ranked:
        lines.append(f"- score={score} [{row['category']}] Q: {row['question']} A: {row['answer']}")
    return "\n".join(lines)


def answer_with_ai_and_db(question: str, gpt_client) -> Dict[str, str | int | None]:
    """Answer by SQL first. Only fallback to LLM when SQL cannot answer confidently."""
    direct = _sql_first_answer(question)
    if direct is not None:
        return direct

    # LLM fallback with SQL retrieval context.
    item_rows = search_active_items(question, limit=12) if _is_item_query(question) else []
    event_rows = search_upcoming_events(question, limit=12) if _is_event_query(question) else []
    context_block = (
        "Use SQL retrieval context below. If context is insufficient, ask one clear follow-up.\n\n"
        f"FAQ candidates:\n{_faq_context_block(question)}\n\n"
        f"Item candidates:\n{_format_items(item_rows, limit=8)}\n\n"
        f"Event candidates:\n{_format_events(event_rows, limit=8)}"
    )

    prompt = (
        "You are SmartSupport AI FAQ bot for a campus second-hand marketplace.\n"
        "Rules:\n"
        "1) SQL context has higher priority than assumptions.\n"
        "2) Keep answer concise and actionable.\n"
        "3) If list requested, return bullets.\n"
        "4) If user asks date/time, include exact datetime from context.\n"
        "5) If unknown, ask one missing detail.\n\n"
        f"User question: {question}\n\n"
        f"{context_block}"
    )

    llm = gpt_client.submit_with_meta(prompt)
    return {
        "text": llm.get("text", ""),
        "latency_ms": llm.get("latency_ms"),
        "model": llm.get("model"),
        "mode": "llm_fallback",
    }
