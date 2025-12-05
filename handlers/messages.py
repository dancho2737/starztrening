from aiogram import Router
from aiogram.types import Message
from ai_responder.responder import ask_ai, sessions

router = Router()

@router.message()
async def handle_message(msg: Message):
    user = msg.from_user.id
    text = (msg.text or "").strip()

    if not text:
        return await msg.answer("Отправьте текстовое сообщение.")

    sessions.add(user, "user", text)

    try:
        answer = await ask_ai(user, text)
        await msg.answer(answer)
    except Exception as e:
        await msg.answer(f"⚠️ Ошибка: <code>{e}</code>")
