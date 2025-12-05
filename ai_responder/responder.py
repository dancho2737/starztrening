# ai_responder/responder.py
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL, LOGS_DIR

# Init OpenAI client
_client_kwargs = {}
if OPENAI_API_KEY:
    _client_kwargs["api_key"] = OPENAI_API_KEY
client = OpenAI(**_client_kwargs)

# Thread executor for sync OpenAI client calls
executor = ThreadPoolExecutor()

# Logging dir
Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)

# Session manager
class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, Dict[str, Any]] = {}

    def get(self, user_id: int) -> Dict[str, Any]:
        return self.sessions.setdefault(user_id, {"state": "idle", "history": [], "last_active": time.time()})

    def set_state(self, user_id: int, state: str):
        self.get(user_id)["state"] = state
        self.get(user_id)["last_active"] = time.time()

    def append_history(self, user_id: int, role: str, content: str):
        entry = {"role": role, "content": content, "ts": time.time()}
        s = self.get(user_id)
        s["history"].append(entry)
        self._write_log(user_id, entry)

    def get_messages(self, user_id: int) -> List[Dict[str, str]]:
        s = self.get(user_id)
        # return history in OpenAI format
        return [{"role": m["role"], "content": m["content"]} for m in s["history"]]

    def _write_log(self, user_id: int, entry: Dict[str, Any]):
        path = Path(LOGS_DIR) / f"{user_id}.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                data = []
        except Exception:
            data = []
        data.append(entry)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

sessions = SessionManager()

# Paths
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
PROMPT_PATH = BASE / "prompts" / "system_prompt.txt"

# Load data
def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

navigation_data = _read_json(DATA_DIR / "navigation.json") or []
rules_data = _read_json(DATA_DIR / "rules.json") or []

def _read_system_prompt() -> str:
    try:
        return (PROMPT_PATH.read_text(encoding="utf-8")).strip()
    except Exception:
        return "Ты — помощник поддержки. Отвечай по базе и проси уточнить при отсутствии данных."

SYSTEM_PROMPT = _read_system_prompt()

# Normalize helper
def normalize(text: str) -> str:
    return (text or "").lower().strip()

# Iterable helpers
def _iter_navigation():
    if isinstance(navigation_data, dict):
        for name, entry in navigation_data.items():
            yield {"name": name, "keywords": entry.get("keywords", []), "hint": entry.get("hint", "")}
    elif isinstance(navigation_data, list):
        for entry in navigation_data:
            if isinstance(entry, dict):
                yield {"name": entry.get("name", ""), "keywords": entry.get("keywords", []), "hint": entry.get("hint", "")}

def _iter_rules():
    if isinstance(rules_data, dict):
        for entry in rules_data.get("rules", []):
            yield entry
    elif isinstance(rules_data, list):
        for entry in rules_data:
            yield entry

# Collect relevant knowledge
def collect_relevant_knowledge(user_question: str) -> List[Dict[str, Any]]:
    q = normalize(user_question)
    results: List[Dict[str, Any]] = []

    # navigation
    for item in _iter_navigation():
        for kw in item.get("keywords", []):
            if not kw:
                continue
            kwn = normalize(kw)
            if kwn in q or q in kwn:
                results.append({"type": "navigation", "name": item.get("name", ""), "hint": item.get("hint", "")})
                break

    # rules
    for entry in _iter_rules():
        for kw in entry.get("keywords", []):
            if not kw:
                continue
            kwn = normalize(kw)
            if kwn in q or q in kwn:
                answer = entry.get("answer") or entry.get("response") or ""
                results.append({"type": "rule", "answer": answer})
                break

    return results

# Build base answer string from found knowledge (used as source for LLM)
def build_base_answer(knowledge: List[Dict[str, Any]]) -> str:
    if not knowledge:
        return ""
    parts = []
    for item in knowledge:
        if item["type"] == "navigation":
            parts.append(f"{item.get('name','Раздел')}: {item.get('hint','')}")
        elif item["type"] == "rule":
            parts.append(item.get("answer",""))
    return "\n\n".join([p for p in parts if p])

# Sync OpenAI call wrapper (runs in thread)
def _sync_chat_call(messages: List[Dict[str, str]], model: str, temperature: float = 0.0) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    # get text from response
    return resp.choices[0].message.content

# Main ask_ai used by handlers
async def ask_ai(user_id: int, question: str) -> str:
    """
    1) ищем по базе;
    2) если найдено >1 вариантов — возвращаем список вариантов и просим уточнить (без LLM);
    3) если найден 1 вариант — формируем источник и переоформляем ответ через LLM строго по источнику;
    4) если не найдено — просим уточнить.
    """
    q = question.strip()
    # find knowledge
    knowledge = collect_relevant_knowledge(q)

    # 0 items
    if not knowledge:
        sessions.set_state(user_id, "awaiting_clarify")
        return "Я не нашёл точного ответа в базе. Можете уточнить вопрос (например, где именно нажимаете или что пытаетесь сделать)?"

    # multiple matches
    if len(knowledge) > 1:
        options = []
        for it in knowledge:
            if it["type"] == "navigation":
                options.append(it.get("name") or it.get("hint", "")[:60])
            else:
                options.append((it.get("answer") or "")[:60])
        sessions.set_state(user_id, "awaiting_clarify")
        opts_text = "\n".join(f"• {o}" for o in options)
        return f"Я нашёл несколько вариантов, уточните, пожалуйста, что именно вы имеете в виду:\n\n{opts_text}\n\nНапишите название раздела или ключевое слово."

    # exactly one
    item = knowledge[0]
    if item["type"] == "navigation":
        source_text = item.get("hint", "")
        source_label = item.get("name", "Раздел")
    else:
        source_text = item.get("answer", "")
        source_label = "Правило"

    base_source = f"Источник ({source_label}):\n{source_text}"

    # prepare messages for LLM: system + assistant(source) + user(question)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": f"Используй ТОЛЬКО следующий источник:\n{base_source}"},
        {"role": "user", "content": f"Вопрос: {q}\n\nОтветь простым человеческим языком, опираясь только на источник выше. Если нужно — попроси уточнить."}
    ]

    loop = asyncio.get_running_loop()
    try:
        answer = await loop.run_in_executor(executor, _sync_chat_call, messages, OPENAI_MODEL, 0.2)
    except Exception as exc:
        return f"⚠️ Ошибка сервиса: {exc}"

    # If answer signals uncertainty, ask for clarification
    low = (answer or "").lower()
    if ("уточн" in low or "не могу" in low or "нужно уточнить" in low) and len(answer) < 200:
        sessions.set_state(user_id, "awaiting_clarify")
        return "Мне нужно чуть больше информации, чтобы точно ответить. Можете уточнить ваш вопрос?"

    # success: log and set awaiting_more
    sessions.append_history(user_id, "user", question)
    sessions.append_history(user_id, "assistant", answer)
    sessions.set_state(user_id, "awaiting_more")
    return answer
