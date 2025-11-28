from aiogram import Router, types
from navigator.navigation_helper import get_navigation_hint
from rule_checker.rules_helper import get_rule_answer
from ai_responder.responder import get_answer

# Считываем системный промпт
with open("prompts/system_prompt.txt", encoding="utf-8") as f:
    system_prompt = f.read()

router = Router()

@router.message()
async def handle_message(message: types.Message):
    """
    Обрабатывает все текстовые сообщения от пользователя.
    Логика:
    1. Сначала ищем подсказку по навигации (navigation.json)
    2. Потом проверяем правила сайта (rules.json)
    3. Если ответа нет, обращаемся к AI (GPT-5-mini) с системным промптом
    """
    user_text = message.text

    # 1. Проверяем навигацию
    hint = get_navigation_hint(user_text)
    if hint:
        await message.answer(hint)
        return

    # 2. Проверяем правила
    rule = get_rule_answer(user_text)
    if rule:
        await message.answer(rule)
        return

    # 3. Используем AI для формирования ответа
    ai_response = get_answer(user_text, system_prompt)
    await message.answer(ai_response)
