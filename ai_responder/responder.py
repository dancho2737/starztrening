# ai_responder/responder.py
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL
import pymorphy2

ROOT = Path(__file__).resolve().parents[1]

# файлы данных
PATH_NAV_DESKTOP = ROOT / "data" / "navigation.json"
PATH_NAV_MOBILE = ROOT / "data" / "navigation_mobile.json"
PATH_RULES = ROOT / "data" / "rules.json"
PATH_PROMPT = ROOT / "prompts" / "system_prompt.txt"

# загрузка json
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

# OpenAI клиент
try:
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    openai_client = None

# морфологический анализатор для лемматизации
morph = pymorphy2.MorphAnalyzer()

# --- Сессии ---
class SessionStore:
    def __init__(self):
        self.history: Dict[int, List[Dict]] = {}
        self.device: Dict[int, str] = {}
        self.pending: Dict[int, List[Dict]] = {}
        self.first_seen: set = set()

    def add_history(self, user_id: int, role: str, content: str):
        self.history.setdefault(user_id, []).append({"role": role, "content": content})

    def get_history(self, user_id: int):
        return self.history.get(user_id, [])

    def add(self, user_id: int, role: str, content: str):
        return self.add_history(user_id, role, content)

    def get(self, user_id: int):
        return self.get_history(user_id)

    def clear(self, user_id: int):
        self.history.pop(user_id, None)
        self.pending.pop(user_id, None)
        self.device.pop(user_id, None)
        self.first_seen.discard(user_id)

    def set_device(self, user_id: int, device: str):
        if device in ("mobile", "desktop"):
            self.device[user_id] = device

    def get_device(self, user_id: int) -> Optional[str]:
        return self.device.get(user_id)

    def has_device(self, user_id: int) -> bool:
        return user_id in self.device

    def set_pending(self, user_id: int, options: List[Dict]):
        self.pending[user_id] = options

    def get_pending(self, user_id: int) -> Optional[List[Dict]]:
        return self.pending.get(user_id)

    def clear_pending(self, user_id: int):
        self.pending.pop(user_id, None)

    def mark_seen(self, user_id: int):
        self.first_seen.add(user_id)

    def was_seen(self, user_id: int) -> bool:
        return user_id in self.first_seen

sessions = SessionStore()
user_device: Dict[int, str] = {}

def _sync_user_device_from_sessions():
    for uid, dev in sessions.device.items():
        user_device[uid] = dev

_sync_user_device_from_sessions()

# --- Утилиты ---
def _title_of(item: Dict, default: str) -> str:
    t = item.get("title") or item.get("name")
    if not t:
        kws = item.get("keywords") or []
        t = kws[0] if kws else default
    return t

def normalize_text(text: str) -> List[str]:
    words = (text or "").lower().split()
    return [morph.parse(w)[0].normal_form for w in words]

# --- Поиск совпадений ---
def search_matches(question: str, device: str) -> List[Dict]:
    q_lemmas = normalize_text(question)
    nav = navigation_mobile if device == "mobile" else navigation_desktop
    matches = []
    exact_matches = []

    for item in nav + rules:
        kws = item.get("keywords", [])
        for kw in kws:
            if not kw: continue
            kw_l = kw.lower().strip()
            if question.lower() == kw_l:
                exact_matches.append(item)
                break
            kw_lemma = morph.parse(kw_l)[0].normal_form
            if kw_lemma in q_lemmas:
                matches.append(item)
                break

    if exact_matches:
        matches = exact_matches

    # удаляем дубликаты
    unique = []
    seen = set()
    for m in matches:
        key = (m.get("type"), m.get("answer") or m.get("hint") or "")
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique

# --- Humanize через GPT ---
def humanize_answer(short_answer: str, user_question: str) -> str:
    if not openai_client:
        return short_answer
    try:
        resp = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Сформулируй коротко и по-человечески ответ на вопрос: {user_question}\n\nИнформация:\n{short_answer}"}
            ],
            temperature=0.2,
        )
        if resp and getattr(resp, "choices", None):
            choice0 = resp.choices[0]
            if hasattr(choice0, "message") and isinstance(choice0.message, dict):
                return choice0.message.get("content") or short_answer
            if hasattr(choice0, "text"):
                return choice0.text or short_answer
        return short_answer
    except Exception:
        return short_answer

# --- ask_ai ---
async def ask_ai(user_id: int, question: str) -> Any:
    q = (question or "").strip()

    # обработка payload device
    if q.startswith("device:"):
        _, val = q.split(":", 1)
        if val in ("mobile", "desktop"):
            sessions.set_device(user_id, val)
            user_device[user_id] = val
            sessions.add_history(user_id, "assistant", f"device_set_{val}")
            return "Отлично! Слушаю вас внимательно, какой будет вопрос?"

    # приветствие и выбор устройства
    if not sessions.was_seen(user_id):
        sessions.mark_seen(user_id)
        sessions.add_history(user_id, "assistant", "greet_asked_device")
        return {
            "text": "Здравствуйте! Выберите устройство:",
            "buttons": [
                {"text": "Смартфон", "data": "device:mobile"},
                {"text": "Компьютер", "data": "device:desktop"}
            ]
        }

    if not sessions.has_device(user_id):
        t = q.lower()
        if any(x in t for x in ("смартфон", "телефон", "mobile", "мобил")):
            sessions.set_device(user_id, "mobile")
            user_device[user_id] = "mobile"
            sessions.add_history(user_id, "assistant", "device_set_mobile")
            return "Отлично! Слушаю вас внимательно, какой будет вопрос?"
        if any(x in t for x in ("компьютер", "пк", "desktop", "ноут")):
            sessions.set_device(user_id, "desktop")
            user_device[user_id] = "desktop"
            sessions.add_history(user_id, "assistant", "device_set_desktop")
            return "Отлично! Слушаю вас внимательно, какой будет вопрос?"
        return "Пожалуйста, выберите устройство: «смартфон» или «компьютер»."

    # pending выбор
    pending = sessions.get_pending(user_id)
    if pending:
        idx = parse_choice(q, pending)
        if idx is None:
            return "Пожалуйста, выберите вариант: номер или напишите фразу полностью."
        selected = pending[idx]
        sessions.clear_pending(user_id)
        answer_val = selected.get("answer") or selected.get("hint") or "Информация отсутствует."
        return humanize_answer(answer_val, question)

    # off-topic
    if is_off_topic(q := question.lower()):
        return "Извините, я могу отвечать только по вопросам сайта."

    device = sessions.get_device(user_id) or "desktop"
    matches = search_matches(q, device)

    # если ничего не найдено — пробуем GPT для понимания смысла
    if not matches and openai_client:
        prompt = f"{SYSTEM_PROMPT}\nПользователь спрашивает: «{q}». Используя данные из navigation и rules, сформулируй ответ."
        try:
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            if resp and getattr(resp, "choices", None):
                choice0 = resp.choices[0]
                text = ""
                if hasattr(choice0, "message") and isinstance(choice0.message, dict):
                    text = choice0.message.get("content", "").strip()
                elif hasattr(choice0, "text"):
                    text = choice0.text.strip()
                if text:
                    return text
        except Exception:
            pass

    if not matches:
        return "Извините, я не смог найти ответ. Попробуйте уточнить вопрос."

    # один вариант
    if len(matches) == 1:
        data = matches[0].get("answer") or matches[0].get("hint") or ""
        if isinstance(data, dict) and "steps" in data:
            lines = [f"{data.get('title','Инструкция')}:"]
            for i, step in enumerate(data["steps"], start=1):
                lines.append(f"{i}. {step}.")
            return "\n".join(lines)
        if isinstance(data, str):
            return humanize_answer(data, question)

    # несколько вариантов
    sessions.set_pending(user_id, matches)
    lines = ["Я нашёл несколько вариантов. Что вы имели в виду:"]
    for i, m in enumerate(matches, start=1):
        typ = "Правило" if m.get("type") == "rules" else "Раздел"
        lines.append(f"{i}) {m.get('title') or '(без названия)'} ({typ})")
    lines.append("Напишите номер варианта или уточните словами.")
    return "\n".join(lines)

# --- Вспомогательные функции parse_choice и is_off_topic ---
def parse_choice(text: str, options: List[Dict]) -> Optional[int]:
    if not text or not options: return None
    t = text.strip().lower()
    map_num = {"1":0,"2":1,"3":2,"4":3,"5":4,"первый":0,"второй":1,"третий":2,"четвёртый":3,"пятый":4}
    if t in map_num and map_num[t] < len(options): return map_num[t]
    for i, opt in enumerate(options):
        title = (opt.get("title") or "").lower()
        if any(word in t for word in title.split()):
            return i
    return None

OFF_TOPIC_KEYWORDS = ["python","код","программа","function","array","массив","счётчик","counter",
                       "for","while","list","class","javascript","java","c++","go","rust","sql","база данных"]

def is_off_topic(question: str) -> bool:
    q = (question or "").lower()
    return any(kw in q for kw in OFF_TOPIC_KEYWORDS)
