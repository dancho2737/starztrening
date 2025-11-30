import json

def load_rules():
    with open("data/rules.json", encoding="utf-8") as f:
        return json.load(f)

rules = load_rules()


def get_rule_answer(user_text: str) -> str | None:
    """Поиск по rules.json"""
    lower = user_text.lower()

    for item in rules:
        if any(kw.lower() in lower for kw in item["keywords"]):
            return item["answer"]

    return None
