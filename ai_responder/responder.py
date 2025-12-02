import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List

from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

from bot.config import OPENAI_API_KEY, OPENAI_MODEL, LOGS_DIR

# ==============================
#  INIT
# ==============================

client = OpenAI(api_key=OPENAI_API_KEY)
executor = ThreadPoolExecutor()

Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)


# ==============================
#  SESSION MANAGER
# ==============================

class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, Dict[str, Any]] = {}

    def get(self, user_id: int) -> Dict[str, Any]:
        return self.sessions.setdefault(user_id, {"history": [], "last_active": time.time()})

    def append_history(self, user_id: int, role: str, content: str):
        entry = {"role": role, "content": content, "ts": time.time()}
        s = self.get(user_id)
        s["history"].append(entry)
        self._write_log(user_id, entry)

    def get_messages(self, user_id: int):
        s = self.get(user_id)
        return [{"role": m["role"], "content": m["content"]} for m in s["history"]]

    def _write_log(self, user_id: int, entry: dict):
        path = Path(LOGS_DIR) / f"{user_id}.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                data = []
        except:
            data = []

        data.append(entry)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


sessions = SessionManager()


# ==============================
#  LOAD JSON DATABASES
# ==============================

BASE_PATH = Path("ai_responder/data")

try:
    navigation_data = json.loads((BASE_PATH / "navigation.json").read_text(encoding="utf-8"))
except:
    navigation_data = {}

try:
    rules_data = json.loads((BASE_PATH / "rules.json").read_text(encoding="utf-8"))
except:
    rules_data = []


# ==============================
#  KNOWLEDGE SEARCH
# ==============================

def normalize(text: str):
    return text.lower().strip()


def collect_relevant_knowledge(user_question: str) -> List[Dict[str, Any]]:
    user_question = normalize(user_question)
    results = []

    # -------- NAVIGATION --------
    for name, entry in navigation_data.items():
        keywords = entry.get("keywords", [])
        for kw in keywords:
            if normalize(kw) in user_question:
                results.append({
                    "type": "navigation",
                    "name": name,
                    "hint": entry.get("hint", "")
                })
                break

    # -------- RULES --------
    for rule in rules_data:
        if not isinstance(rule, dict):
            continue

        keywords = rule.get("keywords", [])
        for kw in keywords:
            if normalize(kw) in user_question:
                results.append({
                    "type": "rule",
                    "answer": rule.get("answer", "")
                })
                break

    return results


# ==============================
#  HUMANIZED RESPONSE BUILDER
# ==============================

def build_response(knowledge: List[Dict[str, Any]], question: str) -> str:
    if not knowledge:
        return (
            "Пока не вижу точной информации по этому вопросу в правилах или навигации. "
            "Но я на связи — уточни, пожалуйста, что именно ты хочешь узнать, и я помогу."
        )

    parts = []

    for item in knowledge:
        if item["type"] == "navigation":
            parts.append(
                f"🔹 *{item['name'].capitalize()}*\n{item['hint']}"
            )
        elif item["type"] == "rule":
            parts.append(item["answer"])

    return "\n\n".join(parts)


# ==============================
#  OPENAI CALL (NEW API, FIXED)
# ==============================

def _sync_chat_call(messages):
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages
    )
    return resp.choices[0].message["content"]


async def ask_ai(user_id: int, question: str):
    # Сначала ищем по базе
    knowledge = collect_relevant_knowledge(question)
    base_answer = build_response(knowledge, question)

    system_prompt = (
        "Ты — дружелюбный помощник поддержки. "
        "Отвечай естественно, живым человеческим языком. "
        "Если информация есть в базе — используй её. "
        "Если нет — попроси уточнить вопрос. "
        "Не выдумывай лишнего."
    )

    msgs = [{"role": "system", "content": system_prompt}]
    msgs += sessions.get_messages(user_id)
    msgs.append({"role": "user", "content": f"Вопрос: {question}\nДанные: {base_answer}"})


    loop = asyncio.get_running_loop()
    try:
        ai_answer = await loop.run_in_executor(executor, _sync_chat_call, msgs)
    except Exception as e:
        return f"Ошибка генерации ответа: {e}"

    return ai_answer
