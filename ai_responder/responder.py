# ai_responder/responder.py
import openai
from config import OPENAI_KEY

openai.api_key = OPENAI_KEY

def get_answer(user_text: str, system_prompt: str) -> str:
    """
    Возвращает ответ ChatGPT на основе системного промпта и текста пользователя.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return "Извините, возникла ошибка при обработке запроса."

