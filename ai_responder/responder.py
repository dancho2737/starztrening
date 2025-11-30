# ai_responder/responder.py
import os
import openai
import asyncio

OPENAI_KEY = os.getenv("OPENAI_KEY")
openai.api_key = OPENAI_KEY

async def get_answer(user_text: str) -> str:
    """
    Возвращает ответ AI на текст пользователя.
    Если OpenAI не понимает вопрос, вернёт уточняющий вопрос.
    """
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_text}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Произошла ошибка при запросе к AI: {e}"
