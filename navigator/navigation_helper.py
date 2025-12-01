import json
import os


DATA_PATH = os.path.join("data", "navigation.json")


def load_navigation():
    """Загружает navigation.json."""
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[navigation_helper] Ошибка загрузки navigation.json: {exc}")
        return {}


def get_navigation():
    """Возвращает весь JSON."""
    return load_navigation()


def find_navigation_by_text(text: str):
    """
    Ищет совпадения по keywords.
    Возвращает список: [(название_раздела, hint), ...]
    """
    text = text.lower().strip()
    nav = load_navigation()
    matches = []

    for name, item in nav.items():
        keywords = item.get("keywords", [])
        hint = item.get("hint", "")

        for kw in keywords:
            if kw.lower() in text:
                matches.append((name, hint))
                break

    return matches
