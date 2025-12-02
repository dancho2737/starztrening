from aiogram import Router, types, F

from ai_responder.responder import sessions, ask_model

# Router
router = Router()

# Загружаем системный промпт
with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()


# ---------------------------------
# КНОПКА "Помощь"
# ---------------------------------
@router.message(F.text == "Помощь")
async def on_help(message: types.Message):
    user_id = message.from_user.id

    # Очищаем историю — новый диалог
    sessions.sessions[user_id] = {"history": []}

    await message.answer(
        "Здравствуйте! 👋\n\nЯ готов помочь вам. Напишите ваш вопрос."
    )


# ---------------------------------
# ОБРАБОТКА ВСЕХ СООБЩЕНИЙ
# ---------------------------------
@router.message()
async def on_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text.strip()

    # Сохраняем запрос пользователя
    sessions.append(user_id, "user", user_text)

    # Отправляем вопрос модели
    reply = await ask_model(
        user_id=user_id,
        system_prompt=SYSTEM_PROMPT,
        user_question=user_text,
    )

    await message.answer(reply)
