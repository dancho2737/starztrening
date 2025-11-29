from aiogram import Router
from aiogram.types import Message

from navigator.navigation_helper import get_navigation_hint
from rule_checker.rules_helper import get_rule_answer
from ai_responder.responder import get_answer

router = Router()

# Загружаем системный промпт
with open("prompts/system_prompt.txt", encoding="utf-8") as file:
    system_prompt = file.read()


@router.message()
async def handle_message(message: Message):
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

    # 3. Ответ GPT
    response = await get_answer(user_text, system_prompt)
    await message.answer(response)
