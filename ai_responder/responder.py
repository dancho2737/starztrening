import os
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=os.getenv("OPENAI_KEY"))


async def get_answer(user_text: str) -> str:
    """Ответ как оператор техподдержки"""
    response = await client.responses.create(
        model="gpt-4o-mini",
        input=f"Ты оператор поддержки. Общайся человечно. Пользователь пишет: {user_text}"
    )

    return response.output_text
