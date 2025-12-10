import json
from pathlib import Path
from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL

# -----------------------
# ПУТИ
# -----------------------
ROOT = Path(__file__).resolve().parents[1]

PATH_PROMPT = ROOT / "prompts" / "system_prompt.txt"

PATH_NAV_DESKTOP = ROOT / "data" / "navigation.json"
PATH_NAV_MOBILE = ROOT / "data" / "navigation_mobile.json"
PATH_RULES = ROOT / "data" / "rules.json"


# -----------------------
# ЗАГРУЗКА JSON
# -----------------------
def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return []


navigation_desktop = load_json(PATH_NAV_DESKTOP)
navigation_mobile = load_json(PATH_NAV_MOBILE)
rules = load_json(PATH_RULES)


# -----------------------
# ПРОМПТ
# -----------------------
try:
    SYSTEM_PROMPT = PATH_PROMPT.read_text(encoding="utf-8")
except:
    SYSTEM_PROMPT = "Ты оператор поддержки. Отвечай строго по базе."


# -----------------------
# СЕССИИ
# -----------------------
class SessionStore:
    def __init__(self):
        self.history = {}
        self.device = {}           # смартфон / компьютер
        self.pending_choice = {}   # ожидаем уточнение

    def add_history(self, user_id, role, content):
        self.history.setdefault(user_id, []).append({"role": role, "content": content})

    def get_history(self, user_id):
        return self.history.get(user_id, [])

    def set_device(self, user_id, device):
        self.device[user_id] = device

    def get_device(self, user_id):
        return self.device.get(user_id)

    def has_device(self, user_id):
        return user_id in self.device

    def set_pending(self, user_id, options):
        self.pending_choice[user_id] = options

    def get_pending(self, user_id):
        return self.pending_choice.get(user_id)

    def clear_pending(self, user_id):
        self.pending_choice.pop(user_id, None)


sessions = SessionStore()


# -----------------------
# ПОИСК СОВПАДЕНИЙ
# -----------------------
def search_matches(question: str, device: str):
    q = question.lower()
    matches = []

    # выбираем навигацию
    nav = navigation_mobile if device == "mobile" else navigation_desktop

    # навигация
    for item in nav:
        for kw in item.get("keywords", []):
            if kw.lower() in q:
                matches.append({
                    "type": "navigation",
                    "title": item.get("title", ""),
                    "value": item.get("hint", "")
                })
                break

    # правила
    for rule in rules:
        for kw in rule.get("keywords", []):
            if kw.lower() in q:
                matches.append({
                    "type": "rules",
                    "title": rule.get("title", ""),
                    "value": rule.get("answer", "")
                })
                break

    return matches


# -----------------------
# ПРЕОБРАЗОВАНИЕ ОТВЕТА ПОЛЬЗОВАТЕЛЯ В НОМЕР
# -----------------------
def parse_user_choice(text: str, options_len: int):
    t = text.strip().lower()

    mapping = {
        "1": 1, "первое": 1,
        "2": 2, "второе": 2,
        "3": 3, "третье": 3,
        "4": 4, "четвертое": 4,
        "5": 5, "пятое": 5,
    }

    if t in mapping and mapping[t] <= options_len:
        return mapping[t] - 1

    for i in range(options_len):
        if str(i + 1) in t:
            return i

    return None


# -----------------------
# ГЛАВНАЯ ФУНКЦИЯ
# -----------------------
async def ask_ai(user_id: int, question: str) -> str:
    
    # ---------- 1. ВЫБОР УСТРОЙСТВА ----------
    if not sessions.has_device(user_id):
        t = question.lower()
        if "смартфон" in t or "телефон" in t or "mobile" in t:
            sessions.set_device(user_id, "mobile")
            return "Отлично! Работаю в мобильном режиме. Задайте ваш вопрос."
        elif "компьютер" in t or "пк" in t or "desktop" in t:
            sessions.set_device(user_id, "desktop")
            return "Понял. Работаю в режиме ПК. Какой у вас вопрос?"

        # если выбор не сделан
        return "Через какое устройство вы заходите? Смартфон или компьютер?"

    device = sessions.get_device(user_id)

    # ---------- 2. ЕСЛИ ЖДЁМ УТОЧНЕНИЕ ----------
    pending = sessions.get_pending(user_id)
    if pending:
        choice = parse_user_choice(question, len(pending))
        if choice is None:
            return "Пожалуйста, выберите один из вариантов (цифра или текст)."

        selected = pending[choice]
        sessions.clear_pending(user_id)
        return selected["value"]

    # ---------- 3. ПОИСК ПО БАЗЕ ----------
    matches = search_matches(question, device)

    if len(matches) == 0:
        return "Мне не удалось найти точный ответ в базе. Уточните, пожалуйста, ваш вопрос."

    if len(matches) == 1:
        return matches[0]["value"]

    # ---------- 4. НЕСКОЛЬКО СОВПАДЕНИЙ — ЗАДАЁМ УТОЧНЕНИЕ ----------
    sessions.set_pending(user_id, matches)

    text = "Я нашёл несколько вариантов. Что вы имеете в виду:\n\n"
    for i, m in enumerate(matches, 1):
        label = "Раздел" if m["type"] == "navigation" else "Правила"
        title = m["title"] or "(без названия)"
        text += f"{i}) {label}: {title}\n"

    return text


# GPT клиент (нужен для истории, если потребуется)
client = OpenAI(api_key=OPENAI_API_KEY)
