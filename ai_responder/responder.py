import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_KEY"))


async def get_answer(user_text: str, system_prompt: str) -> str:
    """
    Асинхронный вызов GPT.
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0.4
        )

        return response.choices[0].message["content"]

    except Exception as e:
        return f"Ошибка AI: {e}"
