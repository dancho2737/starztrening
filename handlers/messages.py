from aiogram import Router
from aiogram.types import Message

from ai_responder.responder import ask_ai, sessions
from bot.config import OPENAI_API_KEY

router = Router()


@router.message()
async def handle_message(msg: Message):
    user_id = msg.from_user.id
    text = msg.text.strip()

    if not text:
        return await msg.answer("Пожалуйста, отправьте текстовое сообщение.")

    try:
        # сохраняем сообщение пользователя в историю
        sessions.append_history(user_id, "user", text)

        # получаем ответ из твоего кастомного движка
        ai_answer = await ask_ai(user_id, text)

        # сохраняем ответ
        sessions.append_history(user_id, "assistant", ai_answer)

        await msg.answer(ai_answer)

    except Exception as e:
        await msg.answer(
            "⚠️ <b>Произошла ошибка при генерации ответа.</b>\n"
            f"Техническая информация: <code>{e}</code>"
        )
