import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import openai  # pip package 'openai'
import asyncio

from bot.config import OPENAI_KEY, OPENAI_MODEL, OPENAI_MAX_TOKENS, OPENAI_TEMPERATURE, LOGS_DIR

openai.api_key = OPENAI_KEY

ROOT = Path(__file__).resolve().parents[1]

# Создаём папку логов если нет
Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)


class SessionManager:
    """
    Простая сессия в памяти. Хранит состояние диалога и историю.
    Для долговременных сессий можно расширить с БД.
    """
    def __init__(self):
        self.sessions: Dict[int, Dict[str, Any]] = {}
        # timeout можно добавить, сейчас в памяти постоянно

    def start_session(self, user_id: int):
        s = {
            "user_id": user_id,
            "state": "idle",
            "history": [],  # list of {'role','text','ts'}
            "last_active": time.time(),
        }
        self.sessions[user_id] = s
        return s

    def get(self, user_id: int) -> Dict[str, Any]:
        if user_id not in self.sessions:
            return self.start_session(user_id)
        self.sessions[user_id]["last_active"] = time.time()
        return self.sessions[user_id]

    def set_state(self, user_id: int, state: str):
        s = self.get(user_id)
        s["state"] = state

    def append_history(self, user_id: int, role: str, text: str):
        s = self.get(user_id)
        s["history"].append({"role": role, "text": text, "ts": time.time()})
        # Также пишем в файл логов
        self._write_log(user_id, role, text)

    def _write_log(self, user_id: int, role: str, text: str):
        path = Path(LOGS_DIR) / f"{user_id}.json"
        entry = {"role": role, "text": text, "ts": time.time()}
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = []
        else:
            data = []
        data.append(entry)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class OpenAIResponder:
    """
    Обёртка для синхронного вызова OpenAI через run_in_executor,
    чтобы не блокировать asyncio loop.
    """
    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt or self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        return (
            "Ты — помощник, который переформулирует ответы, "
            "чтобы они звучали естественно и дружелюбно на русском языке. "
            "Делай ответы краткими, вежливыми. "
            "ОТВЕЧАЙ ТОЛЬКО НА ОСНОВЕ ПРЕДОСТАВЛЕННОЙ ИНФОРМАЦИИ (SOURCE). "
            "Если из SOURCE недостаточно данных — попроси уточнить вопрос. "
            "Ни при каких обстоятельствах не придумывай факты."
        )

    async def rephrase_from_source(self, source_text: str, user_question: str) -> str:
        """
        Принимает source_text (ответ/подсказку из навигации/правил) и вопрос,
        возвращает "человеческий" ответ от модели.
        """
        prompt_messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    "Инструкция: На основе предоставленного SOURCE сформулируй ответ "
                    "для конечного пользователя на русском языке. "
                    "1) Используй только содержание SOURCE. 2) Сформулируй простыми словами. "
                    "3) В конце кратко спроси: 'Есть ли дополнительные вопросы?'\n\n"
                    f"SOURCE:\n{source_text}\n\n"
                    f"Вопрос пользователя: {user_question}\n\n"
                    "Если SOURCE не покрывает вопрос или требуется уточнение — "
                    "ответь коротко 'Нужно уточнить: ...' и предложи варианты уточнений."
                ),
            },
        ]

        # Выполнить синхронный вызов в пуле потоков
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, self._sync_chat_complete, prompt_messages)
        # Вернём только текст
        return response

    def _sync_chat_complete(self, messages: List[Dict[str, str]]) -> str:
        """
        Синхронный вызов OpenAI ChatCompletion. Вынесен отдельной функцией.
        """
        try:
            resp = openai.ChatCompletion.create(
                model=OPENAI_MODEL,
                messages=messages,
                max_tokens=OPENAI_MAX_TOKENS,
                temperature=OPENAI_TEMPERATURE,
            )
            # структура: resp['choices'][0]['message']['content']
            return resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            # Не падаем — возвращаем осмысленную строку об ошибке
            return f"Ошибка при генерации ответа: {str(e)}"

# Экземпляры
sessions = SessionManager()
# загружаем system prompt, если есть файл
_prompt_path = Path(ROOT) / "prompts" / "system_prompt.txt"
_system_prompt = ""
if _prompt_path.exists():
    _system_prompt = _prompt_path.read_text(encoding="utf-8")
responder = OpenAIResponder(system_prompt=_system_prompt)
