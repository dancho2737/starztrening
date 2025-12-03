import json
from aiogram import Router, types
from aiogram.filters import Text

router = Router()

# Загружаем правила из rules.json
with open("rules.json", "r", encoding="utf-8") as f:
    RULES = json.load(f)["rules"]


def find_rule_response(message_text: str):
    """
    Находит подходящий ответ из rules.json на основе ключевых слов.
    """
    text_lower = message_text.lower()

    for rule in RULES:
        for kw in rule["keywords"]:
            if kw.lower() in text_lower:
                return rule["response"]

    return None


@router.message()
async def handle_message(message: types.Message):
    user_text = message.text.strip()

    # Ищем ответ в rules.json
    rule_answer = find_rule_response(user_text)

    if rule_answer:
        await message.answer(rule_answer)
        return

    # Если в rules.json нет подходящего правила — базовый fallback
    await message.answer(
        "Сожалею, но я не нашёл информацию по вашему вопросу. "
        "Попробуйте уточнить формулировку или спросите более конкретно."
    )
