from aiogram import Router, types
from aiogram.filters import Text

from ai_responder.responder import get_answer
from navigator.navigation_helper import get_navigation
from rule_checker.rules_helper import get_rule_answer

router = Router()


@router.message()
async def handle_message(message: types.Message):
    user_text = message.text

    # 1. Проверка правил сайта
    rule_answer = get_rule_answer(user_text)
    if rule_answer:
        await message.answer(rule_answer)
        return

    # 2. Проверка навигации сайта
    navigation_answer = get_navigation(user_text)
    if navigation_answer:
        await message.answer(navigation_answer)
        return

    # 3. Если ничего не найдено → ИИ оператор
    ai_response = await get_answer(user_text)
    await message.answer(ai_response)
