# ai_responder/responder.py
import json
from pathlib import Path
from typing import List, Dict, Optional
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
# This is kept for backwards compatibility with older handlers that import user_device directly.
# Prefer using sessions.set_device / sessions.get_device in new code.
user_device: Dict[int, str] = {}

# keep user_device and sessions in sync if you use both:
def _sync_user_device_from_sessions():
    # populate user_device from sessions.device for compatibility (on import)
    for uid, dev in sessions.device.items():
        user_device[uid] = dev

# initially sync
_sync_user_device_from_sessions()


# вспомогательная функция для получения читабельного заголовка
def _title_of(item: Dict, default: str) -> str:
    # prefer title -> name -> first keyword -> short snippet of hint/answer -> default
    t = item.get("title") or item.get("name")
    if not t:
        kws = item.get("keywords") or []
        if kws:
            t = kws[0]
    if not t:
        txt = item.get("hint") or item.get("answer") or ""
        t = (txt[:60] + "...") if txt else default
    return t


# поиск совпадений
def search_matches(question: str, device: str) -> List[Dict]:
    q = (question or "").lower()
    matches: List[Dict] = []
    if device == "mobile":
        nav = navigation_mobile
    else:
        nav = navigation_desktop

    # навигация
    for item in nav:
        for kw in item.get("keywords", []):
            if kw and kw.lower() in q:
                matches.append({
                    "type": "navigation",
                    "title": _title_of(item, "Навигация"),
                    "value": item.get("hint", "")
                })
                break

    # правила
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        for kw in rule.get("keywords", []):
            if kw and kw.lower() in q:
                matches.append({
                    "type": "rules",
                    "title": _title_of(rule, "Правило"),
                    "value": rule.get("answer", "")
                })
                break

    return matches


# распознать выбор пользователя (номер/слово/фраза)
def parse_choice(text: str, options: List[Dict]) -> Optional[int]:
    if not text or not options:
        return None
    t = text.strip().lower()

    # direct mapping numeric or words
    map_num = {
        "1": 0, "первое": 0, "первый": 0,
        "2": 1, "второе": 1, "второй": 1,
        "3": 2, "третье": 2, "третий": 2,
        "4": 3, "четвёртое": 3, "четвертое": 3, "четвёртый": 3, "четвертый": 3,
        "5": 4, "пятое": 4, "пятый": 4
    }
    if t in map_num and map_num[t] < len(options):
        return map_num[t]

    # direct words 'раздел' or 'правила' preference
    if "правил" in t or "правила" in t or "услов" in t or "можно" in t or "запрещ" in t:
        for i, opt in enumerate(options):
            if opt.get("type") == "rules":
                return i
    if "раздел" in t or "где" in t or "куда" in t or "найти" in t or "странице" in t or "зайти" in t:
        for i, opt in enumerate(options):
            if opt.get("type") == "navigation":
                return i

    # try match by title words
    for i, opt in enumerate(options):
        title = (opt.get("title") or "").lower()
        if title:
            # if any word from title appears in user text
            for word in title.split():
                if word and word in t:
                    return i

    # try to detect number inside text like "2)" or "2."
    for token in t.replace(")", " ").replace(".", " ").split():
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(options):
                return idx

    return None


# off-topic detection (very simple heuristic)
OFF_TOPIC_KEYWORDS = [
    "python", "код", "программа", "function", "array", "массив", "счётчик", "счетчик", "counter",
    "for", "while", "list", "class", "javascript", "java", "c++", "go", "rust", "sql", "база данных"
]


def is_off_topic(question: str) -> bool:
    q = (question or "").lower()
    # if it contains any programming/dev keyword but not site keywords -> consider off-topic
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in q:
            return True
    return False


# humanize via OpenAI optionally (if available) — try/except fallback
def humanize_answer(short_answer: str, user_question: str) -> str:
    if not openai_client:
        return short_answer
    try:
        # Simple rephrase to more human style using chat completions (SDK variant may differ)
        resp = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Сформулируй коротко и по-человечески ответ на вопрос: {user_question}\n\nИнформация:\n{short_answer}"}
            ],
            temperature=0.2,
        )
        # Try to extract text carefully
        if resp and getattr(resp, "choices", None):
            choice0 = resp.choices[0]
            # support different SDK shapes
            if hasattr(choice0, "message") and isinstance(choice0.message, dict):
                return choice0.message.get("content") or short_answer
            if hasattr(choice0, "message") and hasattr(choice0.message, "get"):
                # sometimes message is a mapping-like
                return choice0.message.get("content") or short_answer
            # fallback to .text or .content if present
            if hasattr(choice0, "text"):
                return choice0.text or short_answer
        return short_answer
    except Exception:
        return short_answer


# Главная функция — вызывается из handlers/messages.py
async def ask_ai(user_id: int, question: str) -> str:
    q = (question or "").strip()

    # 1) first contact: greet + ask device
    if not sessions.was_seen(user_id):
        sessions.mark_seen(user_id)
        # greet + device question
        sessions.add_history(user_id, "assistant", "greet_asked_device")
        return (
            "Привет! Я — помощник поддержки. Через какое устройство вы заходите? "
            "Напишите «смартфон» или «компьютер», пожалуйста."
        )

    # 2) device selection (if not selected yet)
    if not sessions.has_device(user_id):
        t = q.lower()
        if any(x in t for x in ("смартфон", "телефон", "mobile", "мобил")):
            sessions.set_device(user_id, "mobile")
            user_device[user_id] = "mobile"
            sessions.add_history(user_id, "assistant", "device_set_mobile")
            return "Отлично — переключаюсь на мобильную навигацию. Введите ваш вопрос."
        if any(x in t for x in ("компьютер", "пк", "desktop", "ноут")):
            sessions.set_device(user_id, "desktop")
            user_device[user_id] = "desktop"
            sessions.add_history(user_id, "assistant", "device_set_desktop")
            return "Хорошо — переключаюсь на версию для компьютера. Введите ваш вопрос."
        # If user didn't select, re-ask
        return "Пожалуйста, укажите устройство: «смартфон» или «компьютер»."

    # 3) if awaiting pending choice
    pending = sessions.get_pending(user_id)
    if pending:
        idx = parse_choice(q, pending)
        if idx is None:
            return "Пожалуйста, выберите вариант: напишите номер (1, 2, ...) или слово 'раздел'/'правила' или точный текст варианта."
        selected = pending[idx]
        sessions.clear_pending(user_id)
        # return the selected value (navigation hint or rule answer)
        answer_text = selected.get("value") or "Информация отсутствует."
        # optionally humanize
        return humanize_answer(answer_text, question)

    # 4) off-topic detection: if question clearly not about site
    if is_off_topic(q):
        return "Извините, я могу отвечать только по вопросам, связанным с работой сайта. Обратитесь по вопросам сайта."

    # 5) normal search
    device = sessions.get_device(user_id) or "desktop"
    matches = search_matches(q, device)

    if not matches:
        # when no match found — politely state it's out of DB and ask to rephrase
        return "Мне не удалось найти точный ответ в базе по этому вопросу. Пожалуйста, уточните, о чём именно идёт речь на сайте."

    if len(matches) == 1:
        answer_text = matches[0].get("value") or "Информация отсутствует."
        return humanize_answer(answer_text, question)

    # multiple matches -> present options and save pending
    sessions.set_pending(user_id, matches)
    lines = ["Я нашёл несколько вариантов. Что вы имеете в виду:"]
    for i, m in enumerate(matches, start=1):
        label = "Правила" if m.get("type") == "rules" else "Раздел"
        title = m.get("title") or "(без названия)"
        lines.append(f"{i}) {title} ({label})")
    lines.append("\nНапишите номер варианта (например, 1 или 2), или слово 'раздел'/'правила', либо напишите фразу, например: 'где на сайте оформить вывод'.")
    return "\n".join(lines)
