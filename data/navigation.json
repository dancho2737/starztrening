# ai_responder/responder.py
import json
import re
import difflib
from pathlib import Path
from typing import List, Dict, Optional, Any
from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL

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

# OpenAI клиент (опционально, если нужен)
try:
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    openai_client = None


# Сессии: история + выбор устройства + ожидаемые варианты
class SessionStore:
    def __init__(self):
        self.history: Dict[int, List[Dict]] = {}
        self.device: Dict[int, str] = {}           # "mobile" / "desktop"
        self.pending: Dict[int, List[Dict]] = {}   # user_id -> list of options
        self.first_seen: set = set()               # чтобы поприветствовать один раз

    # history helpers (new API)
    def add_history(self, user_id: int, role: str, content: str):
        self.history.setdefault(user_id, []).append({"role": role, "content": content})

    def get_history(self, user_id: int):
        return self.history.get(user_id, [])

    # Backwards-compatible methods used by handlers (sessions.add / get / clear)
    def add(self, user_id: int, role: str, content: str):
        """Compatibility: sessions.add(user_id, role, content)"""
        return self.add_history(user_id, role, content)

    def get(self, user_id: int):
        """Compatibility: sessions.get(user_id) -> history list"""
        return self.get_history(user_id)

    def clear(self, user_id: int):
        """Compatibility: clear all user data (history, pending, device, seen)"""
        self.history.pop(user_id, None)
        self.pending.pop(user_id, None)
        self.device.pop(user_id, None)
        self.first_seen.discard(user_id)

    # device
    def set_device(self, user_id: int, device: str):
        if device in ("mobile", "desktop"):
            self.device[user_id] = device

    def get_device(self, user_id: int) -> Optional[str]:
        return self.device.get(user_id)

    def has_device(self, user_id: int) -> bool:
        return user_id in self.device

    # pending
    def set_pending(self, user_id: int, options: List[Dict]):
        self.pending[user_id] = options

    def get_pending(self, user_id: int) -> Optional[List[Dict]]:
        return self.pending.get(user_id)

    def clear_pending(self, user_id: int):
        self.pending.pop(user_id, None)

    # greeting flag
    def mark_seen(self, user_id: int):
        self.first_seen.add(user_id)

    def was_seen(self, user_id: int) -> bool:
        return user_id in self.first_seen


sessions = SessionStore()

# Global map for handlers that import user_device
user_device: Dict[int, str] = {}

def _sync_user_device_from_sessions():
    for uid, dev in sessions.device.items():
        user_device[uid] = dev

_sync_user_device_from_sessions()


def _title_of(item: Dict, default: str) -> str:
    t = item.get("title") or item.get("name")
    if not t:
        kws = item.get("keywords") or []
        if kws:
            t = kws[0]
    if not t:
        txt = item.get("hint") or item.get("answer") or ""
        t = (txt[:60] + "...") if txt else default
    return t


# вспомогательные метрики
def _token_overlap_score(a: str, b: str) -> float:
    a_tokens = set(re.findall(r'\w+', (a or "").lower()))
    b_tokens = set(re.findall(r'\w+', (b or "").lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    inter = a_tokens.intersection(b_tokens)
    return len(inter) / max(len(a_tokens), len(b_tokens))


def _fuzzy_ratio(a: str, b: str) -> float:
    try:
        return difflib.SequenceMatcher(None, a, b).ratio()
    except Exception:
        return 0.0


# Основная функция поиска совпадений — минимальные правки от исходной логики
def search_matches(question: str, device: str) -> List[Dict]:
    """
    Поведение:
      - сначала — точное совпадение по keywords (высший приоритет)
      - затем — вхождение keyword в вопрос
      - затем — token-overlap / fuzzy (поймает опечатки и близкие формулировки)
      - навигация и правила просматриваются одинаково; value = answer (приоритет) или hint
    """
    q_raw = (question or "").strip()
    # нормализуем: пробелы, регистр
    q = re.sub(r'\s+', ' ', q_raw.lower())

    matches: List[Dict] = []
    exact_matches: List[Dict] = []

    nav = navigation_mobile if device == "mobile" else navigation_desktop

    def check_item(item: Dict, item_type: str):
        # value берём из answer (приоритет) -> hint fallback
        val = item.get("answer") if item.get("answer") is not None else item.get("hint", "")
        for kw in item.get("keywords", []) or []:
            kw_l = re.sub(r'\s+', ' ', (kw or "").lower().strip())

            # 1) Точное совпадение — ВЫСШИЙ ПРИОРИТЕТ
            if q == kw_l and kw_l:
                exact_matches.append({
                    "type": item_type,
                    "title": _title_of(item, kw_l),
                    "value": val
                })
                return

            # 2) Простое вхождение ключевого слова
            if kw_l and kw_l in q:
                matches.append({
                    "type": item_type,
                    "title": _title_of(item, kw_l),
                    "value": val
                })
                return

            # 3) Token overlap
            try:
                if _token_overlap_score(q, kw_l) >= 0.4:
                    matches.append({
                        "type": item_type,
                        "title": _title_of(item, kw_l),
                        "value": val
                    })
                    return
            except Exception:
                pass

            # 4) Fuzzy match (опечатки / близкие формы)
            try:
                ratio = _fuzzy_ratio(q, kw_l)
                if ratio >= 0.72:
                    matches.append({
                        "type": item_type,
                        "title": _title_of(item, kw_l),
                        "value": val
                    })
                    return
            except Exception:
                pass

    # 🔹 Навигация
    for item in nav:
        # защита: ожидаем, что nav элемент — dict
        if isinstance(item, dict):
            check_item(item, "navigation")

    # 🔹 Правила
    for rule in rules:
        if isinstance(rule, dict):
            check_item(rule, "rules")

    # 🔥 ЕСЛИ ЕСТЬ ТОЧНОЕ СОВПАДЕНИЕ — ВОЗВРАЩАЕМ ТОЛЬКО ЕГО
    if exact_matches:
        return exact_matches

    # 🧹 Удаляем дубликаты (одинаковый смысл)
    unique = []
    seen = set()
    for m in matches:
        key = (m["type"], str(m["value"]))
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return unique


def parse_choice(text: str, options: List[Dict]) -> Optional[int]:
    if not text or not options:
        return None
    t = text.strip().lower()

    map_num = {
        "1": 0, "первое": 0, "первый": 0,
        "2": 1, "второе": 1, "второй": 1,
        "3": 2, "третье": 2, "третий": 2,
        "4": 3, "четвёртое": 3, "четвертое": 3, "четвёртый": 3, "четвертый": 3,
        "5": 4, "пятое": 4, "пятый": 4
    }
    if t in map_num and map_num[t] < len(options):
        return map_num[t]

    if "правил" in t or "правила" in t or "услов" in t or "можно" in t or "запрещ" in t:
        for i, opt in enumerate(options):
            if opt.get("type") == "rules":
                return i
    if "раздел" in t or "где" in t or "куда" in t or "найти" in t or "странице" in t or "зайти" in t:
        for i, opt in enumerate(options):
            if opt.get("type") == "navigation":
                return i

    for i, opt in enumerate(options):
        title = (opt.get("title") or "").lower()
        if title:
            for word in title.split():
                if word and word in t:
                    return i

    for token in t.replace(")", " ").replace(".", " ").split():
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(options):
                return idx

    return None


OFF_TOPIC_KEYWORDS = [
    "python", "код", "программа", "function", "array", "массив", "счётчик", "счетчик", "counter",
    "for", "while", "list", "class", "javascript", "java", "c++", "go", "rust", "sql", "база данных"
]

def is_off_topic(question: str) -> bool:
    q = (question or "").lower()
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in q:
            return True
    return False


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
            if hasattr(choice0, "message") and hasattr(choice0.message, "get"):
                return choice0.message.get("content") or short_answer
            if hasattr(choice0, "text"):
                return choice0.text or short_answer
        return short_answer
    except Exception:
        return short_answer


# --- Центральная функция: ask_ai (оставлен контракт как в исходнике) ---
async def ask_ai(user_id: int, question: str) -> Any:
    q = (question or "").strip()

    # --- обработка специальных payload'ов (callback data) ---
    if q.startswith("device:"):
        _, val = q.split(":", 1)
        val = val.strip()
        if val in ("mobile", "desktop"):
            sessions.set_device(user_id, val)
            user_device[user_id] = val
            sessions.add_history(user_id, "assistant", f"device_set_{val}")
            return "Отлично! Слушаю вас внимательно, какой будет вопрос?"

    # 1) first contact: greet + ask device (but with buttons)
    if not sessions.was_seen(user_id):
        sessions.mark_seen(user_id)
        sessions.add_history(user_id, "assistant", "greet_asked_device")
        return {
            "text": "Здравствуйте! Выберите, через какое устройство вы пользуетесь:",
            "buttons": [
                {"text": "Смартфон", "data": "device:mobile"},
                {"text": "Компьютер", "data": "device:desktop"}
            ]
        }

    # 2) device selection
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

    # 3) if awaiting pending choice
    pending = sessions.get_pending(user_id)
    if pending:
        idx = parse_choice(q, pending)
        if idx is None:
            return "Пожалуйста, выберите вариант: напишите номер (1, 2, ...) или напишите фразу полностью."
        selected = pending[idx]
        sessions.clear_pending(user_id)
        answer_text = selected.get("value") or "Информация отсутствует."
        # если value — dict со steps, сформируем шаги
        if isinstance(answer_text, dict) and "steps" in answer_text:
            lines = [f"Чтобы {answer_text.get('title')}, выполните следующие шаги:"]
            for i, step in enumerate(answer_text["steps"], start=1):
                lines.append(f"{i}. {step}.")
            return "\n".join(lines)
        return humanize_answer(answer_text, question)

    # 4) off-topic detection
    if is_off_topic(q):
        return "Извините, я могу отвечать только по вопросам, связанным с работой сайта. Обратитесь по вопросам сайта."

    # 5) normal search
    device = sessions.get_device(user_id) or "desktop"
    matches = search_matches(q, device)

    if not matches:
        return "Мне не удалось найти точный ответ в базе по этому вопросу. Пожалуйста, уточните, о чём именно идёт речь на сайте."

    if len(matches) == 1:
        data = matches[0].get("value")

        # Новый формат: title + steps
        if isinstance(data, dict) and "steps" in data:
            lines = [f"Чтобы {data.get('title')}, выполните следующие шаги:"]
            for i, step in enumerate(data["steps"], start=1):
                lines.append(f"{i}. {step}.")
            return "\n".join(lines)

        # Старый формат (строка)
        if isinstance(data, str) and data.strip():
            return humanize_answer(data, question)

        return "Информация по этому вопросу временно недоступна."

    # multiple matches -> present options and save pending
    sessions.set_pending(user_id, matches)
    lines = ["Я нашёл несколько вариантов. Что вы имеете в виду:"]
    for i, m in enumerate(matches, start=1):
        label = "Правила" if m.get("type") == "rules" else "Раздел"
        title = m.get("title") or "(без названия)"
        lines.append(f"{i}) {title} ({label})")
    lines.append("\nНапишите номер варианта (например, 1 или 2), либо напишите фразу полностью.")
    return "\n".join(lines)
