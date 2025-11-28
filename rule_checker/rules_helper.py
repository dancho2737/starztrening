# rule_checker/rules_helper.py
import json

# Загружаем rules.json
with open("data/rules.json", encoding="utf-8") as f:
    rules = json.load(f)

def get_rule_answer(user_text: str) -> str | None:
    """
    Возвращает ответ из правил сайта rules.json по ключевым словам
    """
    user_text_lower = user_text.lower()
    for item in rules:
        if any(kw.lower() in user_text_lower for kw in item["keywords"]):
            return item["answer"]
    return None

