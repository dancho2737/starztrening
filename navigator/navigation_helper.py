import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

DATA_DIR = Path("data")
NAV_FILE = DATA_DIR / "navigation.json"


def get_navigation() -> Dict:
    if not NAV_FILE.exists():
        return {}
    with NAV_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_navigation_by_text(text: str) -> List[Tuple[str, str]]:
    text_l = (text or "").lower()
    nav = get_navigation()
    matches = []
    for name, data in nav.items():
        if not isinstance(data, dict):
            continue
        keywords = data.get("keywords", [])
        hint = data.get("hint", "")
        for kw in keywords:
            if not kw:
                continue
            if kw.lower() in text_l:
                matches.append((name, hint))
                break
    return matches
