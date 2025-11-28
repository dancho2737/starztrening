# navigator/navigation_helper.py
import json

# Загружаем navigation.json
with open("data/navigation.json", encoding="utf-8") as f:
    navigation = json.load(f)

def get_navigation_hint(user_text: str) -> str | None:
    """
    Ищет подсказку по навигации сайта в navigation.json
    """
    user_text_lower = user_text.lower()
    for key, value in navigation.items():
        if any(kw.lower() in user_text_lower for kw in value["keywords"]):
            return value["hint"]
    return None

