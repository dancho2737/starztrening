from aiogram import Router, types
from ai_responder.responder import get_answer  # твоя функция для AI
from navigator.navigation_helper import get_navigation_hint
from rule_checker.rules_helper import get_rule_answer

# Считываем системный промпт
with open("prompts/system_prompt.txt", encoding="utf-8") as f:
    system_prompt = f.read()

router = Router()

@router.message()
async def handle_message(message: types.Message):
    user_text = message.text

    # 1. Навигационные подсказки
    hint = get_navigation_hint(user_text)
    if hint:
        await message.answer(hint)
        return

    # 2. Проверка правил
    rule = get_rule_answer(user_text)
    if rule:
        await message.answer(rule)
        return

    # 3. AI-ответ (человеческий стиль)
    ai_response = get_answer(user_text, system_prompt)
    
    # Если AI считает, что нужно уточнить
    if "не понимаю" in ai_response.lower() or "уточни" in ai_response.lower():
        await message.answer("Извини, я не совсем понял. Можешь уточнить, что именно тебя интересует?")
    else:
        await message.answer(ai_response)
