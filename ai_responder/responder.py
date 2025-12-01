import asyncio
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI


# Инициализация клиента
# На Heroku должна быть переменная окружения: OPENAI_API_KEY
client = OpenAI()

# Пул потоков для синхронных запросов (OpenAI клиент синхронный)
executor = ThreadPoolExecutor()


# -----------------------------------------------------------
# Управление сессиями пользователей
# -----------------------------------------------------------
class SessionManager:
    def __init__(self):
        self.sessions = {}

    def get(self, user_id):
        return self.sessions.setdefault(
            user_id,
            {
                "state": "idle",
                "history": [],  # комментарии пользователя и ответы бота
            },
        )

    def set_state(self, user_id, state):
        self.get(user_id)["state"] = state

    def append_history(self, user_id, sender, text):
        self.get(user_id)["history"].append(
            {
                "sender": sender,
                "text": text,
            }
        )


sessions = SessionManager()


# -----------------------------------------------------------
# СИНХРОННЫЙ вызов ChatGPT (исполняется в ThreadPool)
# -----------------------------------------------------------
def _sync_openai_request(prompt: str) -> str:
    """
    Обычный синхронный запрос к OpenAI (используется через executor)
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",   # можешь заменить на gpt-5-mini если есть доступ
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты — умный помощник сайта. "
                    "Отвечай строго по доступным данным, без домыслов. "
                    "Если данных недостаточно — попроси уточнить вопрос. "
                    "Формулируй ответы естественно, как человек."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    return response.choices[0].message["content"]


# -----------------------------------------------------------
# АСИНХРОННАЯ обёртка для aiogram
# -----------------------------------------------------------
async def responder(user_id: int, source: str, question: str) -> str:
    """
    Главная функция. Её вызывает aiogram в messages.py.
    Она:
    • подготавливает prompt
    • вызывает OpenAI через executor
    • сохраняет историю диалога
    """

    # История пользователя (можешь использовать, если нужно)
    sessions.append_history(user_id, "user", question)

    # Формируем промпт для LLM
    prompt = (
        f"Вот источник информации:\n\n"
        f"{source}\n\n"
        f"Вопрос пользователя: {question}\n\n"
        f"Отвечай строго по источнику. "
        f"Если в источнике нет нужных данных — спроси уточнить вопрос. "
        f"Пиши живым человеческим языком."
    )

    loop = asyncio.get_event_loop()

    try:
        result = await loop.run_in_executor(
            executor,
            _sync_openai_request,
            prompt,
        )
    except Exception as exc:
        return f"Ошибка при генерации ответа: {exc}"

    # Сохраняем в историю
    sessions.append_history(user_id, "assistant", result)

    return result
