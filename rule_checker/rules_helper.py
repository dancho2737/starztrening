import json
import os

DATA_PATH = os.path.join("data", "rules.json")


def load_rules():
    """Загружает rules.json."""
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[rules_helper] Ошибка загрузки rules.json: {exc}")
        return []


def get_rules():
    """Возвращает весь список правил."""
    return load_rules()


def find_rule_by_text(text: str):
    """
    Ищет правила по keywords.
    Возвращает список правил (словарей).
    """
    text = text.lower().strip()
    rules = load_rules()
    matches = []

    for rule in rules:
        keywords = rule.get("keywords", [])
        for kw in keywords:
            if kw.lower() in text:
                matches.append(rule)
                break

    return matches
