# ai_responder/responder.py
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

async def get_openai_answer(user_text: str) -> str:
    """
    Генерация ответа через OpenAI
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты — умный Telegram помощник."},
            {"role": "user", "content": user_text}
        ],
        max_tokens=200
    )

    return response.choices[0].message["content"]
