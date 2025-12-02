import asyncio
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

client = OpenAI()

executor = ThreadPoolExecutor()


class SessionManager:
    def __init__(self):
        self.sessions = {}

    def get(self, user_id):
        return self.sessions.setdefault(
            user_id,
            {"history": []}
        )

    def append(self, user_id, role, text):
        self.get(user_id)["history"].append({"role": role, "content": text})

    def get_history(self, user_id):
        return self.get(user_id)["history"]


sessions = SessionManager()


# -------- СИНХРОННЫЙ GPT-ЗАПРОС --------
def _sync_chat(history):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=history,
        temperature=0.5
    )

    # ИСПРАВЛЕНО!
    return response.choices[0].message.content


# -------- АСИНХРОННЫЙ ИНТЕРФЕЙС --------
async def responder(user_id: int, message: str) -> str:
    """
    Главная функция: полный диалог с GPT.
    """

    # добавляем реплику пользователя в историю
    sessions.append(user_id, "user", message)

    # собираем историю
    history = [
        {
            "role": "system",
            "content": (
                "Ты дружелюбный и умный ассистент. "
                "Отвечай естественно, как человек. "
                "Помогай разбираться с вопросами, давай варианты, "
                "уточняй если что-то непонятно."
            ),
        }
    ] + sessions.get_history(user_id)

    loop = asyncio.get_event_loop()

    try:
        reply = await loop.run_in_executor(executor, _sync_chat, history)
    except Exception as exc:
        reply = f"Ошибка при генерации ответа: {exc}"

    # сохраняем ответ ассистента
    sessions.append(user_id, "assistant", reply)

    return reply
