"""Escalation rule loading helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

RULES_PATH = Path("data/escalation_rules.csv")


def load_escalation_rules(path: Path = RULES_PATH) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def find_rules_by_intent(intent: str, path: Path = RULES_PATH) -> List[Dict[str, str]]:
    rules = []
    for row in load_escalation_rules(path):
        intents = [x.strip() for x in row["trigger_intent"].split("|") if x.strip()]
        if intent in intents:
            rules.append(row)
    return rules
