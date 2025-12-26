# ai_responder/responder.py
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL
import math

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


# -----------------------
# Семантические помощники
# -----------------------
def _cosine(a: List[float], b: List[float]) -> float:
    # защитимся от нулевых векторов
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _collect_candidates(device: str) -> List[Dict]:
    nav = navigation_mobile if device == "mobile" else navigation_desktop
    items: List[Dict] = []
    # нормализуем элементы навигации
    for item in nav:
        items.append({
            "type": "navigation",
            "title": _title_of(item, "Навигация"),
            "keywords": item.get("keywords", []),
            "value": item.get("hint") or item.get("answer", "") or "",
            "_raw": item
        })
    # правила
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        items.append({
            "type": "rules",
            "title": _title_of(rule, "Правило"),
            "keywords": rule.get("keywords", []),
            "value": rule.get("answer", "") or "",
            "_raw": rule
        })
    return items


def _semantic_match_with_embeddings(question: str, device: str, top_k: int = 3) -> List[Dict]:
    """
    Используем embeddings для ранжирования кандидатов по семантическому сходству.
    Возвращаем топ-K совпадений (если похожесть достаточна).
    """
    if not openai_client:
        return []

    try:
        items = _collect_candidates(device)
        if not items:
            return []

        # Формируем тексты для эмбеддингов: title + keywords + snippet
        texts = []
        for it in items:
            kws = " ".join(it.get("keywords") or [])
            snippet = (it.get("value") or "")[:600]  # ограничим длину
            texts.append(f"{it.get('title','')}. {kws}. {snippet}")

        # Запрос batch embeddings
        emb_model = "text-embedding-3-small"  # универсальная модель для эмбеддингов
        resp = openai_client.embeddings.create(model=emb_model, input=[question] + texts)
        if not resp or not getattr(resp, "data", None):
            return []

        # resp.data[0] - embedding для вопроса, остальные - для текстов
        all_emb = [d.embedding for d in resp.data]
        q_emb = all_emb[0]
        item_embs = all_emb[1:]

        # оценим похожесть
        sims = []
        for i, emb in enumerate(item_embs):
            sim = _cosine(q_emb, emb)
            sims.append((i, sim))

        # отсортируем по убыванию похожести
        sims.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, sim in sims[:top_k]:
            # порог — гибкий: берем если sim > 0.62 или если нет других
            if sim < 0.5:
                # слишком слабая похожесть — прерываем (низкая уверенность)
                continue
            it = items[idx]
            results.append({
                "type": it["type"],
                "title": it["title"],
                "value": it["value"],
                "score": sim,
                "_raw": it["_raw"]
            })
        return results
    except Exception:
        return []


def _semantic_match_with_chat(question: str, device: str, top_k: int = 3) -> List[Dict]:
    """
    Если embeddings недоступны, используем chat-модель как "классификатор" —
    просим вернуть номера наиболее подходящих элементов из переданного списка.
    Возвращаем выбранные элементы.
    """
    if not openai_client:
        return []

    try:
        items = _collect_candidates(device)
        if not items:
            return []

        # Ограничим количество кандидатов, чтобы не перегрузить prompt
        max_list = 30
        short_items = items[:max_list]

        # Сформируем список в текстовом виде
        numbered = []
        for i, it in enumerate(short_items, start=1):
            kws = ", ".join(it.get("keywords") or [])
            snippet = (it.get("value") or "")[:300]
            numbered.append(f"{i}. {it['title']} | keywords: {kws} | snippet: {snippet}")

        system = (
            "Ты — помощник, задача которого — по вопросу пользователя выбрать наиболее релевантные элементы "
            "из списка. Верни JSON-массив индексов (1-основной индекс в списке ниже) в порядке убывания релевантности. "
            "Если ничего подходящего нет, верни пустой массив []. Отвечай только JSON, например: [2,5]"
        )

        user = f"Вопрос: {question}\n\nСписок элементов:\n" + "\n".join(numbered) + "\n\nВерни JSON-массив индексов."

        resp = openai_client.chat.completions.create(
            model=OPENAI_MODEL or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.0,
            max_tokens=300,
        )
        if not resp or not getattr(resp, "choices", None):
            return []

        text = None
        choice0 = resp.choices[0]
        # совместимость со структурой ответа разного формата
        if hasattr(choice0, "message") and isinstance(choice0.message, dict):
            text = choice0.message.get("content")
        elif hasattr(choice0, "message") and hasattr(choice0.message, "get"):
            text = choice0.message.get("content")
        elif hasattr(choice0, "text"):
            text = choice0.text

        if not text:
            return []

        # Попробуем извлечь JSON из ответа
        import re
        m = re.search(r"(\[.*\])", text, re.S)
        arr_txt = m.group(1) if m else text.strip()
        try:
            idxs = json.loads(arr_txt)
            if not isinstance(idxs, list):
                return []
        except Exception:
            # если не парсится — попытаться извлечь числа
            nums = re.findall(r"\d+", text)
            idxs = [int(x) for x in nums[:top_k]]

        results = []
        for n in idxs[:top_k]:
            if 1 <= n <= len(short_items):
                it = short_items[n - 1]
                results.append({
                    "type": it["type"],
                    "title": it["title"],
                    "value": it["value"],
                    "_raw": it["_raw"]
                })
        return results
    except Exception:
        return []


# -----------------------
# Основной поиск совпадений
# -----------------------
def search_matches(question: str, device: str) -> List[Dict]:
    """
    Поведение:
    1) сначала — строгое (точное) совпадение по keywords (высший приоритет)
    2) затем — частичное вхождение keyword в вопрос (если kw длинее 3)
    3) если совпадений нет — семантический поиск (embeddings -> chat fallback)
    Возвращаем список объектов:
      { "type": "navigation"|"rules", "title": "...", "value": "...", ... }
    """
    q = (question or "").lower().strip()
    matches = []
    exact_matches = []

    nav = navigation_mobile if device == "mobile" else navigation_desktop

    def check_item(item, item_type):
        for kw in item.get("keywords", []) or []:
            kw_l = (kw or "").lower().strip()

            # 1️⃣ ТОЧНОЕ совпадение — ВЫСШИЙ ПРИОРИТЕТ
            if q == kw_l and kw_l:
                exact_matches.append({
                    "type": item_type,
                    "title": _title_of(item, kw_l),
                    "value": item.get("hint") or item.get("answer", "")
                })
                return

            # 2️⃣ Вопрос длиннее, но ключевая фраза содержится внутри
            if kw_l and kw_l in q and len(kw_l) > 3:
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
        key = (m["type"], str(m["value"]))
        if key not in seen:
            seen.add(key)
            unique.append(m)

    if unique:
        return unique

    # -----------------------
    # НИЖЕ: семантический поиск, если не нашли совпадений по keywords
    # -----------------------
    # Попробуем embeddings (если возможны) — наиболее точный и быстрый вариант
    sem_results = []
    try:
        sem_results = _semantic_match_with_embeddings(q, device, top_k=3)
    except Exception:
        sem_results = []

    # Если embeddings не дали результата, попробуем chat-фоллбек
    if not sem_results:
        try:
            sem_results = _semantic_match_with_chat(q, device, top_k=3)
        except Exception:
            sem_results = []

    # Преобразуем формат в ожидаемый (без score если нет)
    final = []
    seen_vals = set()
    for r in sem_results:
        key = (r.get("type"), str(r.get("value")))
        if key in seen_vals:
            continue
        seen_vals.add(key)
        entry = {
            "type": r.get("type"),
            "title": r.get("title"),
            "value": r.get("value")
        }
        final.append(entry)

    return final


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
    # Переводим / улучшаем ответ "по-человечески" — НО сам контент берётся из базы (short_answer).
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


# --- Новая центральная функция: ask_ai ---
# ВАЖНО: теперь ask_ai может вернуть либо str (как раньше), либо dict с ключами:
#   { "text": "...", "buttons": [ {"text":"Смартфон","data":"device:mobile"}, ... ] }
# Хендлеры должны обработать dict-ответ и отрисовать InlineKeyboard.
async def ask_ai(user_id: int, question: str) -> Any:
    q = (question or "").strip()

    # --- обработка специальных payload'ов (callback data) ---
    # если хендлер отправил callback.data вроде "device:mobile" — поставим устройство
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
        return humanize_answer(answer_text, question)

    # 4) off-topic detection
    if is_off_topic(q):
        return "Извините, я могу отвечать только по вопросам, связанным с работой сайта. Обратитесь по вопросам сайта."

    # 5) normal search
    device = sessions.get_device(user_id) or "desktop"
    matches = search_matches(q, device)

    if not matches:
        # Если ничего не найдено — дружелюбный fallback
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
