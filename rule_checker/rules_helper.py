import json
from pathlib import Path
from typing import List, Dict

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RULES_FILE = DATA_DIR / "rules.json"


def get_rules() -> List[Dict]:
    if not RULES_FILE.exists():
        return []
    with RULES_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_rule_by_text(text: str) -> List[Dict]:
    text_l = (text or "").lower()
    rules = get_rules()
    matches = []
    for r in rules:
        keywords = r.get("keywords", [])
        for kw in keywords:
            if not kw:
                continue
            if kw.lower() in text_l:
                matches.append(r)
                break
    return matches
