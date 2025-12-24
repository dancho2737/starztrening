# ai_responder/responder.py
import json
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


# -----------------------
# Сессии: история + выбор устройства + ожидаемые варианты
# -----------------------
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


# -----------------------
# Утилиты
# -----------------------
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


def _format_answer(answer: Any) -> str:
    """
    Форматирует answer (dict с title+steps или строка) в человекопонятный текст.
    """
    if isinstance(answer, dict):
        title = answer.get("title", "").strip()
        steps = answer.get("steps", []) or []
        lines: List[str] = []
        if title:
            lines.append(f"Чтобы {title}, выполните следующие шаги:")
        for i, s in enumerate(steps, start=1):
            step = str(s).strip().rstrip(".")
            lines.append(f"{i}. {step}.")
        return "\n".join(lines).strip() if lines else "Информация отсутствует."
    if isinstance(answer, str):
        txt = answer.strip()
        return txt if txt else "Информация отсутствует."
    return "Информация отсутствует."


def _safe_value_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    except Exception:
        return str(value)


def _truncate_to_telegram(s: str, limit: int = 3800) -> str:
    if not isinstance(s, str):
        s = str(s)
    return s if len(s) <= limit else s[:limit] + "..."


# -----------------------
# Поиск совпадений (оставил логику как у тебя)
# -----------------------
def search_matches(question: str, device: str) -> List[Dict]:
    q = (question or "").lower().strip()
    matches = []
    exact_matches = []

    nav = navigation_mobile if device == "mobile" else navigation_desktop

    def check_item(item, item_type):
        for kw in item.get("keywords", []):
            kw_l = (kw or "").lower().strip()

            # 1️⃣ ТОЧНОЕ совпадение — ВЫСШИЙ ПРИОРИТЕТ
            if q == kw_l:
                exact_matches.append({
                    "type": item_type,
                    "title": _title_of(item, kw_l),
                    "value": item.get("hint") or item.get("answer", "")
                })
                return

            # 2️⃣ Вопрос длиннее, но ключевая фраза содержится внутри
            if kw_l in q and len(kw_l) > 3:
                matches.append({
                    "type": item_type,
                    "title": _title_of(item, kw_l),
                    "value": item.get("hint") or item.get("answer", "")
                })
                return

    # 🔹 Навигация
    for item in nav:
        check_item(item, "navigation")

    # 🔹 Правила
    for rule in rules:
        check_item(rule, "rules")

    # 🔥 ЕСЛИ ЕСТЬ ТОЧНОЕ СОВПАДЕНИЕ — ВОЗВРАЩАЕМ ТОЛЬКО ЕГО
    if exact_matches:
        return exact_matches

    # 🧹 Удаляем дубликаты (одинаковый смысл)
    unique = []
    seen = set()
    for m in matches:
        key = (m["type"], _safe_value_key(m["value"]))
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return unique


# -----------------------
# Вспомогательные: parse_choice, is_off_topic, humanize_answer
# -----------------------
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


def _extract_choice_content(choice) -> str:
    """
    Вытаскивает текст из choice в разных вариантах SDK:
    - предпочтительно: choice.message.content
    - fallback: choice.get('message', {}).get('content') (if dict-like)
    - иначе: пустая строка (чтобы не возвращать объект)
    """
    try:
        # новый/объектный стиль
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            content = choice.message.content
            return content.strip() if isinstance(content, str) else ""
        # старый dict-like
        if isinstance(choice, dict):
            msg = choice.get("message") or choice.get("text") or ""
            if isinstance(msg, dict):
                return (msg.get("content") or "").strip()
            if isinstance(msg, str):
                return msg.strip()
        # иногда есть поле 'text'
        if hasattr(choice, "text"):
            txt = getattr(choice, "text")
            return txt.strip() if isinstance(txt, str) else ""
    except Exception:
        pass
    return ""


def humanize_answer(short_answer: str, user_question: str) -> str:
    """
    Используем OpenAI только для перефразирования коротких строковых ответов.
    Защита:
      - не передаём в OpenAI структурированные steps
      - обрезаем вход/выход под лимит Telegram
    """
    if not openai_client:
        return _truncate_to_telegram(short_answer)

    # если short_answer слишком большой — не шлём полностью
    MAX_IN = 1500
    safe_input = (short_answer or "")
    if not isinstance(safe_input, str):
        safe_input = str(safe_input)
    if len(safe_input) > MAX_IN:
        safe_input = safe_input[:MAX_IN] + "..."

    try:
        resp = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Сформулируй коротко и по-человечески ответ на вопрос: {user_question}\n\nИнформация:\n{safe_input}"}
            ],
            temperature=0.2,
            max_tokens=400,
        )
        if resp and getattr(resp, "choices", None):
            choice0 = resp.choices[0]
            text = _extract_choice_content(choice0)
            if text:
                return _truncate_to_telegram(text)
    except Exception:
        pass

    return _truncate_to_telegram(short_answer)


# -----------------------
# NEW: ask_gpt_for_intent — использует OpenAI чтобы выбрать подходящую запись из candidates
# -----------------------
def ask_gpt_for_intent(user_text: str, candidates: List[str]) -> Optional[int]:
    """
    Просит модель выбрать индекс (0-based) наиболее подходящего варианта из candidates.
    Возвращает индекс или None.
    Модель просят ответить ТОЛЬКО числом (1..N) или 0 если ни один не подходит.
    """
    if not openai_client or not candidates:
        return None

    # Ограничим кандидатов для экономии токенов
    max_cand = 30
    cand = candidates[:max_cand]
    numbered = "\n".join([f"{i+1}. {c}" for i, c in enumerate(cand)])
    prompt = (
        "Ты — помощник службы поддержки. Пользователь задал вопрос. Выбери ЛУЧШИЙ вариант из списка, "
        "который соответствует намерению пользователя. Ответь ТОЛЬКО числом: номер варианта (1, 2, ...) или 0 если ничего не подходит.\n\n"
        f"Запрос пользователя:\n\"{user_text}\"\n\n"
        "Варианты:\n" + numbered + "\n\n"
        "Ответ (только число):"
    )

    try:
        resp = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=6,
        )
        if resp and getattr(resp, "choices", None):
            choice0 = resp.choices[0]
            text = _extract_choice_content(choice0)
            # извлекаем первое число
            for token in text.replace("\n", " ").split():
                if token.isdigit():
                    num = int(token)
                    if num == 0:
                        return None
                    if 1 <= num <= len(cand):
                        return num - 1
    except Exception:
        return None
    return None


# -----------------------
# Основная функция: ask_ai
# -----------------------
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
            # ответ после нажатия кнопки
            return "Отлично! Слушаю вас внимательно, какой будет вопрос?"

    # 1) first contact: greet + ask device (but with buttons)
    if not sessions.was_seen(user_id):
        sessions.mark_seen(user_id)
        sessions.add_history(user_id, "assistant", "greet_asked_device")
        # Возвращаем структуру с кнопками — хендлер должен отрисовать InlineKeyboard.
        return {
            "text": "Здравствуйте! Выберите, через какое устройство вы пользуетесь:",
            "buttons": [
                {"text": "Смартфон", "data": "device:mobile"},
                {"text": "Компьютер", "data": "device:desktop"}
            ]
        }

    # 2) device selection (если пользователь всё ещё печатает слово)
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
        # форматируем ответ (dict или str)
        formatted = _format_answer(answer_text)
        # humanize только для коротких строковых ответов
        if openai_client and isinstance(answer_text, str) and len(formatted) < 1500:
            return humanize_answer(formatted, question)
        return formatted if len(formatted) <= 3500 else formatted[:3500] + "..."

    # 4) off-topic detection
    if is_off_topic(q):
        return "Извините, я могу отвечать только по вопросам, связанным с работой сайта. Обратитесь по вопросам сайта."

    # 5) normal search by keywords
    device = sessions.get_device(user_id) or "desktop"
    matches = search_matches(q, device)

    # 6) Если не найдено совпадений — используем GPT, чтобы понять намерение и выбрать подходящий раздел
    if not matches:
        # Собираем candidates (title + краткое описание) из navigation (текущая версия) и rules
        items_map: List[Dict] = []
        candidates: List[str] = []

        nav = navigation_mobile if device == "mobile" else navigation_desktop
        combined = (nav or []) + (rules or [])

        # Создаём компактные кандидаты: title + первые keywords (если есть)
        for item in combined:
            ans = item.get("answer")
            if isinstance(ans, dict):
                title = ans.get("title") or _title_of(item, "Без названия")
            else:
                title = item.get("title") or _title_of(item, "Без названия")

            kw_excerpt = ""
            kws = item.get("keywords") or []
            if kws:
                kw_excerpt = ", ".join(kws[:3])
            else:
                if isinstance(ans, dict):
                    steps = ans.get("steps", []) or []
                    if steps:
                        kw_excerpt = str(steps[0])[:80]
                elif isinstance(ans, str):
                    kw_excerpt = ans[:80]

            candidate_text = f"{title}" + (f" — {kw_excerpt}" if kw_excerpt else "")
            candidates.append(candidate_text)
            items_map.append(item)

        # спросим GPT, какой индекс подходит
        idx = ask_gpt_for_intent(q, candidates) if openai_client else None

        if idx is not None and 0 <= idx < len(items_map):
            selected_item = items_map[idx]
            answer_val = selected_item.get("answer") or selected_item.get("hint") or ""
            formatted = _format_answer(answer_val)
            if openai_client and isinstance(answer_val, str) and len(formatted) < 1500:
                return humanize_answer(formatted, q)
            return formatted if len(formatted) <= 3500 else formatted[:3500] + "..."

        # Если GPT не выбрал ничего — даём общий humanize по контексту (если доступен), иначе сообщение
        if openai_client:
            ctx_parts = []
            max_items = 40
            count = 0
            for item in combined:
                if count >= max_items:
                    break
                ans = item.get("answer") or item.get("hint") or ""
                title = _title_of(item, "Без названия")
                if isinstance(ans, dict) and "steps" in ans:
                    steps = ans.get("steps", []) or []
                    steps_text = " / ".join([str(s).strip().rstrip(".") for s in steps[:5]])
                    part = f"{title}: {steps_text}"
                elif isinstance(ans, str):
                    part = f"{title}: {ans.strip()[:200]}"
                else:
                    part = title
                ctx_parts.append(part)
                count += 1
            context_text = "\n\n".join(ctx_parts) if ctx_parts else "Информация по базе отсутствует."
            if len(context_text) > 1500:
                context_text = context_text[:1500] + "..."
            return humanize_answer(context_text, question)

        return "Мне не удалось найти точный ответ в базе по этому вопросу. Пожалуйста, уточните, о чём именно идёт речь на сайте."

    # 7) если найдено ровно одно совпадение (по keywords)
    if len(matches) == 1:
        data = matches[0].get("value")

        # Новый формат: title + steps -> строго без OpenAI
        if isinstance(data, dict) and "steps" in data:
            return _format_answer(data)

        # Старый формат (строка)
        if isinstance(data, str) and data.strip():
            if openai_client and len(data) < 1500:
                return humanize_answer(data, question)
            return data.strip() if len(data.strip()) <= 3500 else data.strip()[:3500] + "..."

        return "Информация по этому вопросу временно недоступна."

    # 8) multiple matches -> present options and save pending
    sessions.set_pending(user_id, matches)
    lines = ["Я нашёл несколько вариантов. Что вы имеете в виду:"]
    for i, m in enumerate(matches, start=1):
        label = "Правила" if m.get("type") == "rules" else "Раздел"
        title = m.get("title") or "(без названия)"
        lines.append(f"{i}) {title} ({label})")
    lines.append("\nНапишите номер варианта (например, 1 или 2), либо напишите фразу полностью.")
    return "\n".join(lines)
