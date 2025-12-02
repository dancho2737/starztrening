from aiogram import Router, types
from aiogram.filters import Text

from ai_responder.responder import sessions, ask_model

# Router
router = Router()

# Подгружаем system_prompt
with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()


# -------------------------------
# КНОПКА "Помощь"
# -------------------------------
@router.message(Text("Помощь"))
async def on_help(message: types.Message):
    user_id = message.from_user.id

    # Очищаем историю диалога — новый сеанс
    sessions.sessions[user_id] = {"history": []}

    await message.answer(
        "Здравствуйте! 👋\n\nЯ готов помочь вам. Напишите, пожалуйста, ваш вопрос."
    )


# -------------------------------
# ВСЕ ТЕКСТОВЫЕ СООБЩЕНИЯ
# -------------------------------
@router.message()
async def on_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()

    # Добавляем сообщение пользователя в историю
    sessions.append(user_id, "user", user_text)

    # Генерируем ответ модели
    reply = await ask_model(
        user_id=user_id,
        system_prompt=SYSTEM_PROMPT,
        user_question=user_text,
    )

    await message.answer(reply)
