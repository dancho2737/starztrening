import json

def load_navigation():
    with open("data/navigation.json", encoding="utf-8") as f:
        return json.load(f)

navigation = load_navigation()


def get_navigation(user_text: str) -> str | None:
    """Поиск подсказок в navigation.json"""
    lower = user_text.lower()

    for item in navigation:
        if any(kw.lower() in lower for kw in item["keywords"]):
            return item["answer"]

    return None
