# ai_responder/responder.py
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL, LOGS_DIR

# init
_client_kwargs = {}
if OPENAI_API_KEY:
    _client_kwargs["api_key"] = OPENAI_API_KEY
client = OpenAI(**_client_kwargs)

executor = ThreadPoolExecutor()
Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)

# sessions
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

    def get_messages(self, user_id: int) -> List[Dict[str, str]]:
        s = self.get(user_id)
        return [{"role": m["role"], "content": m["content"]} for m in s["history"]]

    def _write_log(self, user_id: int, entry: dict):
        path = Path(LOGS_DIR) / f"{user_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except Exception:
            data = []
        data.append(entry)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

sessions = SessionManager()

# load data
BASE_PATH = Path("ai_responder/data")
PROMPT_PATH = Path("ai_responder/prompts/system_prompt.txt")

def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

navigation_data = _read_json(BASE_PATH / "navigation.json") or []
rules_data = _read_json(BASE_PATH / "rules.json") or []

def _read_system_prompt() -> str:
    try:
        return (PROMPT_PATH.read_text(encoding="utf-8")).strip()
    except Exception:
        # fallback default
        return (
            "Ты — помощник поддержки. Отвечай коротко, по факту и только по данным из базы. "
            "Если данных нет — попроси уточнить. Не придумывай."
        )

SYSTEM_PROMPT = _read_system_prompt()

# utilities
def normalize(text: str) -> str:
    return (text or "").lower().strip()

def _iter_navigation():
    """Yield items uniformly: dicts with 'keywords' and 'hint' and optionally 'name'."""
    if isinstance(navigation_data, dict):
        # format: {name: {keywords:..., hint:...}}
        for name, entry in navigation_data.items():
            yield {"name": name, "keywords": entry.get("keywords", []), "hint": entry.get("hint", "")}
    elif isinstance(navigation_data, list):
        for entry in navigation_data:
            # support both {name, keywords, hint} and {keywords, hint}
            if isinstance(entry, dict):
                yield {
                    "name": entry.get("name") or entry.get("title") or "",
                    "keywords": entry.get("keywords", []),
                    "hint": entry.get("hint", "") or entry.get("description", "")
                }

def _iter_rules():
    """Yield rules uniformly: dicts with 'keywords' and 'answer'."""
    if isinstance(rules_data, dict):
        # possibly wrapped like {"rules": [...]}
        for entry in rules_data.get("rules", []):
            yield entry
    elif isinstance(rules_data, list):
        for entry in rules_data:
            yield entry

# knowledge search (robust)
def collect_relevant_knowledge(user_question: str) -> List[Dict[str, Any]]:
    q = normalize(user_question)
    results: List[Dict[str, Any]] = []

    # navigation search
    for item in _iter_navigation():
        for kw in item.get("keywords", []):
            if not kw:
                continue
            kwn = normalize(kw)
            if kwn in q or q in kwn:
                results.append({"type": "navigation", "name": item.get("name", ""), "hint": item.get("hint", "")})
                break

    # rules search
    for entry in _iter_rules():
        kws = entry.get("keywords", [])
        for kw in kws:
            if not kw:
                continue
            kwn = normalize(kw)
            if kwn in q or q in kwn:
                # support multiple answer keys
                answer = entry.get("answer") or entry.get("response") or entry.get("rules") or ""
                results.append({"type": "rule", "answer": answer})
                break

    return results

def build_base_answer(knowledge: List[Dict[str, Any]]) -> str:
    if not knowledge:
        return ""
    parts = []
    for item in knowledge:
        if item["type"] == "navigation":
            name = item.get("name") or "Раздел"
            parts.append(f"{name}: {item.get('hint','')}")
        elif item["type"] == "rule":
            parts.append(item.get("answer",""))
    return "\n\n".join(p for p in parts if p)

# OpenAI call (executor)
def _sync_chat_call(messages: List[Dict[str, str]], model: str, temperature: float = 0.0) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature
    )
    # new OpenAI returns Pydantic objects; access via attributes
    return resp.choices[0].message.content

async def ask_ai(user_id: int, question: str, model: Optional[str] = None, temperature: float = 0.0) -> str:
    model = model or OPENAI_MODEL
    knowledge = collect_relevant_knowledge(question)
    base_answer = build_base_answer(knowledge)
    # build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # optionally include a short assistant message explaining source
    if base_answer:
        messages.append({"role": "assistant", "content": f"Источник информации:\n{base_answer}"})
    # include user history (if any)
    history = sessions.get_messages(user_id)
    if history:
        # keep history but avoid enormous payloads
        # we include last up to 6 messages
        messages += history[-6:]
    messages.append({"role": "user", "content": question})

    loop = asyncio.get_running_loop()
    try:
        answer = await loop.run_in_executor(executor, _sync_chat_call, messages, model, temperature)
    except Exception as exc:
        return f"⚠️ Ошибка генерации ответа: {exc}"
    # log
    sessions.append_history(user_id, "user", question)
    sessions.append_history(user_id, "assistant", answer)
    return answer
