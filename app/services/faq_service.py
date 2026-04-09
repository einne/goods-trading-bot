"""FAQ loading and lookup helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

FAQ_PATH = Path("data/faq_seed.csv")


def load_faq(path: Path = FAQ_PATH) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def get_faq_by_id(faq_id: int, path: Path = FAQ_PATH) -> Dict[str, str] | None:
    for row in load_faq(path):
        if int(row["id"]) == faq_id:
            return row
    return None
