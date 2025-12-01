import asyncio
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI


# Создаём клиент OpenAI (ключ уже должен быть в переменных окружения: OPENAI_API_KEY)
client = OpenAI()

# Пул потоков для выполнения синхронных запросов OpenAI
executor = ThreadPoolExecutor()


class SessionManager:
    def __init__(self):
        self.sessions = {}

    def get(self, user_id):
        return self.sessions.setdefault(user_id, {"state": "idle", "history": []})

    def set_state(self, user_id, state):
        self.get(user_id)["state"] = state

    def append_history(self, user_id, sender, text):
        self.get(user_id)["history"].append({"sender": sender, "text": text})


sessions = SessionManager()


# ------------------------------
# Функция синхронного OpenAI-запроса
# ------------------------------
def _sync_openai_request(prompt: str) -> str:
    """
    Вызов ChatGPT в синхронном режиме.
    Этот код запускается в отдельном потоке.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # можешь заменить на gpt-5-mini если есть доступ
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты — умный помощник сайта. Отвечай строго и только по источнику. "
                    "Если информации в источнике недостаточно — проси уточнить вопрос. "
                    "Формулируй ответ естественно, как живой человек."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    return response.choices[0].message["content"]


# ------------------------------
# Асинхронная обёртка для aiogram
# ------------------------------
async def rephrase_from_source(source: str, question: str) -> str:
    """
    Асинхронная функция — безопасно вызывает OpenAI внутри aiogram
    """

    prompt = (
        f"Вот единственный источник информации:\n\n"
        f"{source}\n\n"
        f"Вопрос пользователя: {question}\n\n"
        "Ответь строго по источнику, но нормальным человеческим языком. "
        "Не добавляй ничего от себя."
    )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, _sync_openai_request, prompt)
        return result
    except Exception as exc:
        return f"Ошибка при генерации ответа: {exc}"
