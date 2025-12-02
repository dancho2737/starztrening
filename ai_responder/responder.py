import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL, LOGS_DIR

# OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# executor
executor = ThreadPoolExecutor()

# Создаем папку логов
Path(LOGS_DIR).mkdir(exist_ok=True, parents=True)


# ==============================
# SESSION MANAGER
# ==============================
class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, Dict[str, Any]] = {}

    def get(self, user_id: int) -> Dict[str, Any]:
        return self.sessions.setdefault(user_id, {"history": []})

    def append(self, user_id: int, role: str, text: str):
        s = self.get(user_id)
        s["history"].append({"role": role, "content": text})

    def history_messages(self, user_id: int):
        return [
            {"role": h["role"], "content": h["content"]}
            for h in self.get(user_id)["history"]
        ]


sessions = SessionManager()


# ==============================
# LOAD JSON KNOWLEDGE BASE
# ==============================
def load_json_file(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


NAV_DATA = load_json_file("data/navigation.json")
RULE_DATA = load_json_file("data/rules.json")


def collect_relevant_knowledge(question: str) -> str:
    """Найти все подходящие правила и навигацию по частичному совпадению"""
    q_lower = question.lower()
    collected = []

    def check(entry):
        for kw in entry.get("keywords", []):
            if kw.lower() in q_lower:
                return True
        return False

    for item in NAV_DATA:
        if check(item):
            collected.append(f"[НАВИГАЦИЯ] {item.get('answer', '')}")

    for item in RULE_DATA:
        if check(item):
            collected.append(f"[ПРАВИЛО] {item.get('answer', '')}")

    # Если нет совпадений — отправим ВСЕ (модель выберет нужное)
    if not collected:
        for item in NAV_DATA:
            collected.append(f"[НАВИГАЦИЯ] {item.get('answer', '')}")
        for item in RULE_DATA:
            collected.append(f"[ПРАВИЛО] {item.get('answer', '')}")

    return "\n".join(collected)


# ==============================
# OPENAI REQUEST
# ==============================
def sync_chat_call(messages):
    """Синхронный вызов модели"""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=1,  # GPT-4o-mini использует только 1
    )
    return resp.choices[0].message.content


async def ask_model(user_id: int, system_prompt: str, user_question: str) -> str:
    """Основной метод генерации ответа"""
    history = sessions.history_messages(user_id)
    knowledge = collect_relevant_knowledge(user_question)

    system_msg = {"role": "system", "content": system_prompt}

    knowledge_msg = {
        "role": "assistant",
        "content": f"ИНФОРМАЦИЯ ДЛЯ ОТВЕТА:\n{knowledge}\n\nИспользуй только эти данные."
    }

    user_msg = {"role": "user", "content": user_question}

    messages = [system_msg] + history + [knowledge_msg, user_msg]

    try:
        loop = asyncio.get_running_loop()
        answer = await loop.run_in_executor(executor, sync_chat_call, messages)
    except Exception as e:
        return f"Ошибка при генерации ответа: {e}"

    # Записываем историю
    sessions.append(user_id, "user", user_question)
    sessions.append(user_id, "assistant", answer)

    return answer
