import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any

from openai import OpenAI

from bot.config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE, LOGS_DIR

# Инициализация клиента (поддерживает OPENAI_API_KEY)
_client_kwargs = {}
if OPENAI_API_KEY:
    _client_kwargs["api_key"] = OPENAI_API_KEY
client = OpenAI(**_client_kwargs)

# executor для синхронного клиента
executor = ThreadPoolExecutor()

# Логи
Path(LOGS_DIR).mkdir(exist_ok=True, parents=True)


class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, Dict[str, Any]] = {}

    def get(self, user_id: int) -> Dict[str, Any]:
        return self.sessions.setdefault(user_id, {"state": "idle", "history": []})

    def set_state(self, user_id: int, state: str):
        self.get(user_id)["state"] = state
        self.get(user_id)["last_active"] = time.time()

    def append_history(self, user_id: int, role: str, text: str):
        s = self.get(user_id)
        s["history"].append({"role": role, "content": text, "ts": time.time()})
        self._flush_log(user_id, {"role": role, "content": text, "ts": time.time()})

    def get_history_messages(self, user_id: int) -> List[Dict[str, str]]:
        """
        Возвращает history в формате сообщений для OpenAI: список dict(role, content).
        """
        s = self.get(user_id)
        msgs = []
        for item in s.get("history", []):
            msgs.append({"role": item["role"], "content": item["content"]})
        return msgs

    def _flush_log(self, user_id: int, entry: Dict[str, Any]):
        path = Path(LOGS_DIR) / f"{user_id}.json"
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = []
        except Exception:
            data = []
        data.append(entry)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


sessions = SessionManager()


# синхронный вызов OpenAI (выполняется в executor)
def _sync_chat_call(messages: List[Dict[str, str]]) -> str:
    """
    messages: список {'role': 'system'|'user'|'assistant', 'content': '...'}
    Возвращает строку ответа (content).
    """
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=OPENAI_TEMPERATURE,
    )
    # new SDK: message is an object
    return resp.choices[0].message.content


async def ask_model(user_id: int, system_prompt: str, source: str, user_question: str) -> str:
    """
    Собирает сообщения и асинхронно вызывает модель.
    system_prompt — дополнительные инструкции (строго / human-like).
    source — текст источника (hint/answer из JSON).
    user_question — исходный вопрос пользователя.
    """
    # История пользователя + system
    # Формируем messages: system, (history), assistant/source, user(question)
    history_msgs = sessions.get_history_messages(user_id)

    # system prompt + explicit SOURCE assistant message
    system_msg = {"role": "system", "content": system_prompt}
    source_msg = {
        "role": "assistant",
        "content": f"SOURCE:\n{source}\n\n(В ответах используйте ТОЛЬКО эту информацию как источник.)"
    }
    user_msg = {"role": "user", "content": user_question}

    messages = [system_msg] + history_msgs + [source_msg, user_msg]

    loop = asyncio.get_running_loop()
    try:
        answer = await loop.run_in_executor(executor, _sync_chat_call, messages)
    except Exception as exc:
        return f"Ошибка при генерации ответа: {exc}"

    return answer
