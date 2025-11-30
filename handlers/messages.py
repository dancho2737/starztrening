# handlers/messages.py
from aiogram import Router, types
from ai_responder.responder import get_answer
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# Инлайн-кнопка "Спросить ИИ Ассистента"
async def ask_ai_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="Спросить ИИ Ассистента", callback_data="ask_ai"))
    return keyboard

@router.message()
async def handle_user_message(message: types.Message):
    """
    Обработка любого текста от пользователя.
    Отправляет сначала кнопку для уточнения, потом ответ AI.
    """
    # Показываем кнопку пользователю
    keyboard = await ask_ai_keyboard()
    await message.answer("Нажмите, чтобы спросить ИИ Ассистента:", reply_markup=keyboard)

@router.callback_query(lambda c: c.data == "ask_ai")
async def handle_ai_callback(callback: types.CallbackQuery):
    """
    Вызывается при нажатии на кнопку "Спросить ИИ Ассистента".
    """
    await callback.answer()  # Убираем "часики" на кнопке
    user_text = callback.message.text or "Привет"
    answer = await get_answer(user_text)
    await callback.message.answer(answer)
