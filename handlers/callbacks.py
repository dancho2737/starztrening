from aiogram import Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from ai_responder.responder import get_answer

router = Router()

# Обработчик нажатия на кнопку "Спросить ИИ Ассистента"
@router.callback_query()
async def ai_button_handler(callback: types.CallbackQuery):
    user_text = callback.message.text  # берем текст из сообщения, на которое нажали
    system_prompt_path = "prompts/system_prompt.txt"
    
    # Читаем системный промпт
    with open(system_prompt_path, encoding="utf-8") as f:
        system_prompt = f.read()
    
    # Получаем ответ от AI
    ai_response = get_answer(user_text, system_prompt)
    
    await callback.message.answer(ai_response)
    await callback.answer()  # чтобы убрать "часики" на кнопке
