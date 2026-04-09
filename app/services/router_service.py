"""Main response router based on FAQ, intent, and escalation data."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from services.escalation_service import find_rules_by_intent
from services.faq_service import get_faq_by_id
from services.intent_service import match_intent


def _split_keywords(keyword_blob: str) -> List[str]:
    return [k.strip().lower() for k in keyword_blob.split(",") if k.strip()]


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _pick_escalation_rule(intent_name: str, message: str) -> Dict[str, str] | None:
    rules = find_rules_by_intent(intent_name)
    if not rules:
        return None

    msg = _normalize_text(message)
    scored_rules: List[Tuple[int, int, int, Dict[str, str]]] = []
    for rule in rules:
        keywords = _split_keywords(rule.get("trigger_keywords", ""))
        keyword_hits = sum(1 for kw in keywords if kw in msg)
        priority = int(rule.get("priority", "3"))
        level_str = rule.get("escalation_level", "L1").upper()
        level_num = int(level_str[1:]) if len(level_str) > 1 and level_str[1:].isdigit() else 1
        scored_rules.append((keyword_hits, priority, level_num, rule))

    # If at least one rule has keyword evidence, pick strongest matched rule.
    matched = [item for item in scored_rules if item[0] > 0]
    if matched:
        matched.sort(key=lambda item: (item[0], -item[1], item[2]), reverse=True)
        return matched[0][3]

    # No keyword evidence: fall back to lowest-risk default route.
    scored_rules.sort(key=lambda item: (item[1], item[2]))
    return scored_rules[0][3]


def _pick_human_handoff_rule(intent_name: str) -> Dict[str, str] | None:
    rules = find_rules_by_intent(intent_name)
    if not rules:
        return None

    for rule in rules:
        if rule.get("target_queue") == "HumanSupport":
            return rule

    rules.sort(
        key=lambda rule: (
            int(rule.get("priority", "3")),
            int(rule.get("escalation_level", "L1")[1:])
            if len(rule.get("escalation_level", "L1")) > 1 and rule.get("escalation_level", "L1")[1:].isdigit()
            else 1,
        )
    )
    return rules[0]


def route_message(
    message: str,
    intents: List[Dict[str, str]],
) -> Dict[str, str] | None:
    matched_intent = match_intent(message, intents)
    if matched_intent is None:
        return None

    route = matched_intent.get("route", "faq")
    faq_id = int(matched_intent.get("faq_id", "0"))
    faq = get_faq_by_id(faq_id)

    if route == "faq" and faq:
        return {
            "mode": "faq",
            "intent": matched_intent["intent"],
            "faq_id": str(faq_id),
            "response": (
                f"{faq['answer']}\n\n"
                "If your issue is unresolved, reply with: human support"
            ),
        }

    if route in {"escalate", "human"}:
        rule = (
            _pick_human_handoff_rule(matched_intent["intent"])
            if route == "human"
            else _pick_escalation_rule(matched_intent["intent"], message)
        )
        if rule:
            response = (
                "Your case has been escalated.\n"
                f"Level: {rule['escalation_level']}\n"
                f"Queue: {rule['target_queue']}\n"
                f"SLA: within {rule['sla_minutes']} minutes.\n"
                "Please provide your order number and relevant screenshots."
            )
            return {
                "mode": "escalation",
                "intent": matched_intent["intent"],
                "faq_id": str(faq_id),
                "rule_id": rule["id"],
                "response": response,
            }

        fallback = (
            "A human support ticket is created for you. "
            "Please share your order number and a short issue summary."
        )
        return {
            "mode": "human",
            "intent": matched_intent["intent"],
            "faq_id": str(faq_id),
            "response": fallback,
        }

    return None
