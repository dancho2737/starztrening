# ai_responder/responder.py
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL

ROOT = Path(__file__).resolve().parents[1]

# -------------------- paths --------------------
PATH_NAV_DESKTOP = ROOT / "data" / "navigation.json"
PATH_NAV_MOBILE = ROOT / "data" / "navigation_mobile.json"
PATH_RULES = ROOT / "data" / "rules.json"
PATH_PROMPT = ROOT / "prompts" / "system_prompt.txt"


# -------------------- loaders --------------------
def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


navigation_desktop = load_json(PATH_NAV_DESKTOP)
navigation_mobile = load_json(PATH_NAV_MOBILE)
rules = load_json(PATH_RULES)

try:
    SYSTEM_PROMPT = PATH_PROMPT.read_text(encoding="utf-8")
except Exception:
    SYSTEM_PROMPT = "Ты — оператор поддержки. Отвечай строго по базе."

try:
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    openai_client = None


# -------------------- sessions --------------------
class SessionStore:
    def __init__(self):
        self.history = {}
        self.device = {}
        self.pending = {}
        self.first_seen = set()

    def add(self, user_id, role, content):
        self.history.setdefault(user_id, []).append({"role": role, "content": content})

    def clear(self, user_id):
        self.history.pop(user_id, None)
        self.pending.pop(user_id, None)
        self.device.pop(user_id, None)
        self.first_seen.discard(user_id)

    def set_device(self, user_id, device):
        if device in ("mobile", "desktop"):
            self.device[user_id] = device

    def get_device(self, user_id):
        return self.device.get(user_id)

    def has_device(self, user_id):
        return user_id in self.device

    def set_pending(self, user_id, options):
        self.pending[user_id] = options

    def get_pending(self, user_id):
        return self.pending.get(user_id)

    def clear_pending(self, user_id):
        self.pending.pop(user_id, None)

    def mark_seen(self, user_id):
        self.first_seen.add(user_id)

    def was_seen(self, user_id):
        return user_id in self.first_seen


sessions = SessionStore()
user_device: Dict[int, str] = {}


# -------------------- helpers --------------------
def _title_of(item: Dict, default: str) -> str:
    if item.get("title"):
        return item["title"]
    if item.get("keywords"):
        return item["keywords"][0]
    return default


def format_answer(data: Any) -> str:
    if isinstance(data, dict) and "steps" in data:
        lines = [f"Чтобы {data.get('title')}, выполните следующие шаги:"]
        for i, step in enumerate(data["steps"], 1):
            lines.append(f"{i}. {step}.")
        return "\n".join(lines)
    if isinstance(data, str):
        return data.strip()
    return "Информация отсутствует."


# -------------------- keyword search --------------------
def search_matches(question: str, device: str) -> List[Dict]:
    q = question.lower()
    nav = navigation_mobile if device == "mobile" else navigation_desktop
    matches = []

    for source, typ in [(nav, "navigation"), (rules, "rules")]:
        for item in source:
            for kw in item.get("keywords", []):
                if kw.lower() in q:
                    matches.append({
                        "type": typ,
                        "title": _title_of(item, kw),
                        "value": item.get("answer") or item.get("hint")
                    })
                    break
    return matches


# -------------------- AI semantic search --------------------
def ai_semantic_match(question: str, device: str) -> Optional[Dict]:
    if not openai_client:
        return None

    nav = navigation_mobile if device == "mobile" else navigation_desktop
    pool = nav + rules

    compact = [
        {
            "keywords": item.get("keywords", []),
            "title": item.get("title"),
        }
        for item in pool
    ]

    try:
        resp = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты анализируешь вопрос пользователя и выбираешь ОДИН "
                        "подходящий раздел базы знаний. "
                        "Ответь ТОЛЬКО ключевой фразой из keywords или NONE."
                    )
                },
                {
                    "role": "user",
                    "content": f"Вопрос:\n{question}\n\nБаза:\n{json.dumps(compact, ensure_ascii=False)}"
                }
            ]
        )

        text = resp.choices[0].message.content.strip().lower()
        if text == "none":
            return None

        for item in pool:
            for kw in item.get("keywords", []):
                if kw.lower() in text:
                    return {
                        "type": "navigation",
                        "title": _title_of(item, kw),
                        "value": item.get("answer") or item.get("hint")
                    }
    except Exception:
        return None

    return None


# -------------------- main --------------------
async def ask_ai(user_id: int, question: str) -> Any:
    q = question.strip()

    if q.startswith("device:"):
        val = q.split(":", 1)[1]
        sessions.set_device(user_id, val)
        user_device[user_id] = val
        return "Отлично! Какой у вас вопрос?"

    if not sessions.was_seen(user_id):
        sessions.mark_seen(user_id)
        return {
            "text": "Здравствуйте! Выберите устройство:",
            "buttons": [
                {"text": "Смартфон", "data": "device:mobile"},
                {"text": "Компьютер", "data": "device:desktop"},
            ]
        }

    if not sessions.has_device(user_id):
        return "Пожалуйста, укажите устройство: смартфон или компьютер."

    device = sessions.get_device(user_id)

    pending = sessions.get_pending(user_id)
    if pending:
        idx = int(q) - 1 if q.isdigit() else None
        if idx is not None and 0 <= idx < len(pending):
            sessions.clear_pending(user_id)
            return format_answer(pending[idx]["value"])
        return "Введите номер варианта."

    matches = search_matches(q, device)

    if not matches:
        ai_match = ai_semantic_match(q, device)
        if ai_match:
            return format_answer(ai_match["value"])
        return "Не удалось найти информацию. Попробуйте переформулировать вопрос."

    if len(matches) == 1:
        return format_answer(matches[0]["value"])

    sessions.set_pending(user_id, matches)
    lines = ["Я нашёл несколько вариантов:"]
    for i, m in enumerate(matches, 1):
        lines.append(f"{i}) {m['title']}")
    return "\n".join(lines)
