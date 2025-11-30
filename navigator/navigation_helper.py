# navigator/navigation_helper.py
import json
import os

# Загружаем navigation.json
navigation_path = os.path.join("data", "navigation.json")
with open(navigation_path, encoding="utf-8") as f:
    navigation_data = json.load(f)

def get_navigation_hint(user_text: str) -> str | None:
    """
    Ищет подсказку по ключевым словам в navigation.json
    """
    user_text_lower = user_text.lower()
    for item_key, item_value in navigation_data.items():
        if any(kw.lower() in user_text_lower for kw in item_value.get("keywords", [])):
            return item_value.get("hint")
    return None
