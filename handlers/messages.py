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
        # 🔥 Новый правильный вызов OpenAI (chat.completions)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "user", "content": user_text}
            ],
            temperature=1
        )

        ai_answer = response.choices[0].message.content

        await msg.answer(ai_answer)

    except Exception as e:
        await msg.answer(
            "⚠️ <b>Произошла ошибка при генерации ответа.</b>\n"
            f"Техническая информация: <code>{e}</code>"
        )
