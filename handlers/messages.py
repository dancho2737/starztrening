from aiogram import Router
from aiogram.types import Message
from bot.config import OPENAI_API_KEY, OPENAI_MODEL
from openai import OpenAI

router = Router()
client = OpenAI(api_key=OPENAI_API_KEY)


@router.message()
async def handle_message(msg: Message):
    try:
        # Генерация текста через OpenAI Responses API
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=msg.text
        )

        ai_answer = response.output_text

        await msg.answer(ai_answer)

    except Exception as e:
        await msg.answer(f"Ошибка генерации ответа: {e}")
