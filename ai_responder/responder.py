# ai_responder/responder.py
import json
import re
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


# --- Утилиты форматирования ответа ---
def format_answer(answer: Any) -> str:
    """
    Превращает answer (dict с title+steps или строку) в текст.
    Гарантирует, что вернётся непустая строка.
    """
    if isinstance(answer, dict):
        title = answer.get("title", "").strip()
        lines = []
        if title:
            lines.append(title)
            lines.append("")  # пустая строка после заголовка
        steps = answer.get("steps", [])
        for i, step in enumerate(steps, start=1):
            # убираем завершающие пробелы и точки — добавляем точку единообразно
            s = str(step).strip().rstrip(".")
            lines.append(f"{i}. {s}")
        return "\n".join(lines).strip()
    # если это строка
    if isinstance(answer, str):
        text = answer.strip()
        return text if text else "Информация отсутствует."
    return "Информация отсутствует."


def normalize_text(t: str) -> str:
    return (t or "").lower().strip()


# простая токенизация (отделяем слова, убираем короткие стоп-слова)
def tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    # заменим не буквенно-цифровые символы на пробелы
    text = re.sub(r"[^\wа-яё0-9]+", " ", text, flags=re.IGNORECASE)
    tokens = [t for t in text.split() if len(t) > 1]
    return tokens


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
        txt = item.get("hint") or ""
        # если answer строка, использовать её начало
        if isinstance(item.get("answer"), str):
            txt = item.get("answer")
        t = (txt[:60] + "...") if txt else default
    return t


def safe_value_key(value: Any) -> str:
    """
    Возвращает строковый ключ для value, чтобы можно было использовать в set/dedup.
    Если value dict/list — сериализуем, иначе str().
    """
    try:
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        return str(value)
    except Exception:
        return str(value)


def search_matches(question: str, device: str) -> List[Dict]:
    """
    Ищет совпадения по keywords в navigation (mobile/desktop) и rules.
    Возвращает список объектов вида {'type': 'navigation'|'rules', 'title': ..., 'value': ...}
    value может быть строкой или dict (title+steps).
    """
    q = normalize_text(question)
    matches = []
    exact_matches = []

    nav = navigation_mobile if device == "mobile" else navigation_desktop

    def check_item(item, item_type):
        for kw in item.get("keywords", []):
            kw_l = (kw or "").lower().strip()
            if not kw_l:
                continue

            # точное совпадение
            if q == kw_l:
                exact_matches.append({
                    "type": item_type,
                    "title": _title_of(item, kw_l),
                    "value": item.get("answer") or item.get("hint", "")
                })
                return

            # частичное вхождение
            if kw_l in q and len(kw_l) > 3:
                matches.append({
                    "type": item_type,
                    "title": _title_of(item, kw_l),
                    "value": item.get("answer") or item.get("hint", "")
                })
                return

    # навигация
    for item in nav:
        check_item(item, "navigation")

    # правила
    for rule in rules:
        check_item(rule, "rules")

    # если есть точные совпадения — вернуть только их
    if exact_matches:
        return exact_matches

    # удаляем дубликаты по (type, value_key)
    unique = []
    seen = set()
    for m in matches:
        key = (m["type"], safe_value_key(m.get("value")))
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
    """
    Существующее поведение: если есть openai_client — даём ему переформулировать строковый ответ.
    short_answer должен быть строкой.
    """
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


# --- Новая функция: определение intent через GPT ---
def ask_gpt_for_intent(user_text: str, candidates: List[str]) -> Optional[int]:
    """
    Попросить GPT выбрать наилучший вариант из candidates.
    Возвращает индекс (0-based) выбранного варианта, либо None.
    Мы просим GPT вернуть ТОЛЬКО номер (1..N) или 0 если нет подходящего варианта.
    Это уменьшает вероятность неверной интерпретации.
    """
    if not openai_client or not candidates:
        return None

    # ограничим количество кандидатов (например, 30), чтобы не превышать длину prompt
    max_cand = 30
    cand = candidates[:max_cand]

    numbered = "\n".join([f"{i+1}. {c}" for i, c in enumerate(cand)])
    prompt = (
        "Ты ассистент службы поддержки. По запросу пользователя выбери НАИЛУЧШИЙ вариант "
        "из списка. Ответь ТОЛЬКО числом — номер варианта (1, 2, ...) или 0 если ни один не подходит.\n\n"
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
            max_tokens=12
        )
        if resp and getattr(resp, "choices", None):
            text = ""
            choice0 = resp.choices[0]
            # разбор разных форматов ответа
            if hasattr(choice0, "message") and isinstance(choice0.message, dict):
                text = (choice0.message.get("content") or "").strip()
            elif hasattr(choice0, "text"):
                text = (choice0.text or "").strip()
            else:
                text = str(choice0)
            # ищем цифру в ответе (может быть "1", "1.", "1)" и т.д.)
            # также допускаем, что GPT может написать номер словами ("one") — но это редкость
            # простая обработка: найти первое вхождение числа
            for token in re.split(r"[\s\)\.]+", text):
                token = token.strip()
                if token.isdigit():
                    num = int(token)
                    if num == 0:
                        return None
                    if 1 <= num <= len(cand):
                        return num - 1
            # если не нашли цифру — попытаться найти число внутри всей строки
            m = re.search(r"\d+", text)
            if m:
                num = int(m.group())
                if 1 <= num <= len(cand):
                    return num - 1
            return None
    except Exception:
        return None
    return None


def simple_semantic_match(user_q: str, items: List[Dict], top_k: int = 1) -> Optional[int]:
    """
    Быстрый эвристический скоринг: считает пересечение токенов между запросом и candidate text
    (title + keywords + небольшая выжимка из steps).
    Возвращает индекс лучшего совпадения, если он достаточно явный (по порогам), иначе None.
    Это экономит вызовы GPT и ловит большинство живых формулировок.
    """
    q_tokens = set(tokenize(user_q))
    if not q_tokens:
        return None

    scores = []
    for idx, item in enumerate(items):
        # формируем candidate text
        ans = item.get("answer")
        kand = []
        if isinstance(ans, dict):
            kand.append(ans.get("title") or "")
            # добавим короткую выжимку из первых шагов (если есть)
            steps = ans.get("steps", [])
            if steps:
                kand.append(" ".join(steps[:2]))
        else:
            kand.append(str(ans or ""))
        keywords = item.get("keywords") or []
        kand.extend(keywords)
        candidate_text = " ".join([k for k in kand if k])
        cand_tokens = set(tokenize(candidate_text))
        if not cand_tokens:
            scores.append((idx, 0, 0.0))
            continue
        shared = q_tokens.intersection(cand_tokens)
        shared_count = len(shared)
        ratio = shared_count / (len(q_tokens) if q_tokens else 1)
        scores.append((idx, shared_count, ratio))

    # найдем лучший
    scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
    if not scores:
        return None
    best_idx, best_count, best_ratio = scores[0]

    # пороги: явный матч — либо >=2 совпавших токена, либо 1 совпадение но при этом доля >= 0.35
    if best_count >= 2 or (best_count >= 1 and best_ratio >= 0.35):
        return best_idx
    return None


# --- Новая центральная функция: ask_ai ---
# ВАЖНО: теперь ask_ai может вернуть либо str (как раньше), либо dict с ключами:
#   { "text": "...", "buttons": [ {"text":"Смартфон","data":"device:mobile"}, ... ] }
# Хендлеры должны обработать dict-ответ и отрисовать InlineKeyboard.
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
        answer_val = selected.get("value") or "Информация отсутствует."
        # format and return
        text = format_answer(answer_val)
        # optional humanize for final polish
        if openai_client and isinstance(answer_val, str):
            return humanize_answer(text, question)
        return text

    # 4) off-topic detection
    if is_off_topic(q):
        return "Извините, я могу отвечать только по вопросам, связанным с работой сайта. Обратитесь по вопросам сайта."

    # 5) normal search
    device = sessions.get_device(user_id) or "desktop"
    matches = search_matches(q, device)

    # 5a) если ничего не найдено по ключевым словам — попробуем быстрый семантический матч
    if not matches:
        nav = navigation_mobile if device == "mobile" else navigation_desktop
        items = nav + rules

        # сначала быстрый эвристический матч (локально, без OpenAI)
        sem_idx = simple_semantic_match(q, items)
        if sem_idx is not None:
            selected_item = items[sem_idx]
            answer_val = selected_item.get("answer") or "Информация отсутствует."
            text = format_answer(answer_val)
            if openai_client and isinstance(answer_val, str):
                return humanize_answer(text, q)
            return text

        # если быстрый локальный матч не дал результата, пробуем GPT как детектор намерения
        # собираем candidates: комбинируем title + keywords + краткое описание (если есть)
        candidates = []
        items_map = []  # параллельный список, чтобы вернуть объект
        for item in items:
            ans = item.get("answer")
            keywords = item.get("keywords") or []
            # candidate_text: title + keywords + short steps snippet
            if isinstance(ans, dict):
                title = ans.get("title") or ""
                steps = ans.get("steps", [])
                snippet = " ".join(steps[:2]) if steps else ""
            else:
                title = str(ans or "")
                snippet = ""
            candidate_text = " ".join([title] + keywords + [snippet]).strip()
            if not candidate_text:
                # fallback: try to use first keyword or generated title
                fallback_title = item.get("title") or (item.get("keywords") or [None])[0] or _title_of(item, "option")
                candidate_text = str(fallback_title)
            candidates.append(candidate_text)
            items_map.append(item)

        # вызов GPT для выбора индекса
        idx = ask_gpt_for_intent(q, candidates)
        if idx is not None and 0 <= idx < len(items_map):
            selected_item = items_map[idx]
            answer_val = selected_item.get("answer") or "Информация отсутствует."
            text = format_answer(answer_val)
            # optional: humanize textual answer only if it's a string (to avoid double-format)
            if openai_client and isinstance(answer_val, str):
                return humanize_answer(text, q)
            return text

        # если и GPT не помог — возвратим дефолтный ответ
        return "Мне не удалось найти точный ответ в базе по этому вопросу. Пожалуйста, уточните, о чём именно идёт речь на сайте."

    # 6) если найдено ровно одно совпадение (по keywords)
    if len(matches) == 1:
        data = matches[0].get("value")

        # если value - dict с steps/title
        if isinstance(data, dict) and "steps" in data:
            text = format_answer(data)
            return text

        # старый формат (строка)
        if isinstance(data, str) and data.strip():
            # сначала форматируем (на случай, если нужна правка), затем даём humanize
            text = format_answer(data)
            if openai_client:
                return humanize_answer(text, q)
            return text

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
