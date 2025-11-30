from aiogram import Router, types
from navigator.navigation_helper import get_navigation_hint
from rule_checker.rules_helper import get_rule_answer
from ai_responder.responder import get_answer
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

with open("prompts/system_prompt.txt", encoding="utf-8") as f:
    system_prompt = f.read()

router = Router()

@router.message()
async def handle_message(message: types.Message):
    user_text = message.text

    # 1. Проверка навигации
    hint = get_navigation_hint(user_text)
    if hint:
        await message.answer(hint)
        return

    # 2. Проверка правил
    rule = get_rule_answer(user_text)
    if rule:
        await message.answer(rule)
        return

    # 3. Ответ от AI с кнопкой
    ai_response = get_answer(user_text, system_prompt)
    
    # Создаем кнопку "Спросить ИИ Ассистента"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Спросить ИИ Ассистента", callback_data="ask_ai")]
    ])
    
    await message.answer(ai_response, reply_markup=keyboard)
