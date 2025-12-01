import json
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
NAV_FILE = DATA_DIR / "navigation.json"


def get_navigation() -> Dict:
    if not NAV_FILE.exists():
        return {}
    with NAV_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_navigation_by_text(text: str) -> List[Tuple[str, str]]:
    """
    Возвращает список кортежей (section_name, hint) где найдено совпадение keywords.
    """
    nav = get_navigation()
    text_l = (text or "").lower()
    matches = []
    for section_name, section_data in nav.items():
        if not isinstance(section_data, dict):
            continue
        keywords = section_data.get("keywords", [])
        hint = section_data.get("hint", "")
        for kw in keywords:
            if not kw:
                continue
            if kw.lower() in text_l:
                matches.append((section_name, hint))
                break
    return matches
