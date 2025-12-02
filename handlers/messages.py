from aiogram import Router, types
from ai_responder.responder import ask_ai, sessions

router = Router()

@router.message()
async def user_message(msg: types.Message):
    user_id = msg.from_user.id
    text = msg.text.strip()

    # Записываем вопрос в историю
    sessions.append_history(user_id, "user", text)

    ai_answer = await ask_ai(user_id, text)

    # Запись ответа в историю
    sessions.append_history(user_id, "assistant", ai_answer)

    await msg.answer(ai_answer)
