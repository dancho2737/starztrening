# handlers/messages.py
from aiogram import Router
from aiogram.types import Message
from ai_responder.responder import ask_ai, sessions

router = Router()

@router.message()
async def handle_message(msg: Message):
    user_id = msg.from_user.id
    text = (msg.text or "").strip()
    if not text:
        return await msg.answer("Пожалуйста, отправьте текстовое сообщение.")

    # mark in session that user asked
    sessions.append_history(user_id, "user", text)

    try:
        answer = await ask_ai(user_id, text)
        # final reply
        await msg.answer(answer)
    except Exception as e:
        await msg.answer(
            "⚠️ Произошла ошибка при генерации ответа.\n"
            f"Техническая информация: {e}"
        )
