from aiogram import Router
from aiogram.types import Message
from bot.config import OPENAI_API_KEY, OPENAI_MODEL
from openai import OpenAI

router = Router()
client = OpenAI(api_key=OPENAI_API_KEY)


@router.message()
async def handle_message(msg: Message):
    user_text = msg.text.strip()

    if not user_text:
        return await msg.answer("Пожалуйста, отправьте текстовое сообщение.")

    try:
        # Отправляем запрос в OpenAI
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=user_text
        )

        # Всегда безопасно вытаскиваем ответ
        ai_answer = response.output_text or "Не удалось получить ответ."

        await msg.answer(ai_answer)

    except Exception as e:
        await msg.answer(
            "⚠️ <b>Произошла ошибка при генерации ответа.</b>\n"
            f"Техническая информация: <code>{e}</code>"
        )
