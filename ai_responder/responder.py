import json
from pathlib import Path
from openai import OpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL

# -----------------------
# ПУТИ К ФАЙЛАМ
# -----------------------
ROOT = Path(__file__).resolve().parents[1]

PATH_NAV = ROOT / "data" / "navigation.json"
PATH_RULES = ROOT / "data" / "rules.json"
PATH_PROMPT = ROOT / "prompts" / "system_prompt.txt"


# -----------------------
# ЗАГРУЗКА JSON
# -----------------------
def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return []


navigation = load_json(PATH_NAV)
rules = load_json(PATH_RULES)

try:
    SYSTEM_PROMPT = PATH_PROMPT.read_text(encoding="utf-8")
except:
    SYSTEM_PROMPT = "Ты оператор поддержки. Отвечай строго по базе."


# -----------------------
# ПОИСК ИНФО ИЗ БАЗЫ
# -----------------------
def search_knowledge(question: str):
    q = question.lower()
    results = []

    # поиск по навигации
    for item in navigation:
        for kw in item.get("keywords", []):
            if kw.lower() in q:
                results.append(item["hint"])
                break

    # поиск по правилам
    for rule in rules:
        for kw in rule.get("keywords", []):
            if kw.lower() in q:
                results.append(rule.get("answer", ""))
                break

    return "\n\n".join(results)


# -----------------------
# GPT КЛИЕНТ
# -----------------------
client = OpenAI(api_key=OPENAI_API_KEY)


# -----------------------
# СЕССИИ (диалоги)
# -----------------------
class SessionStore:
    def __init__(self):
        self.data = {}

    def add(self, user_id, role, content):
        self.data.setdefault(user_id, []).append({"role": role, "content": content})

    def get(self, user_id):
        return self.data.get(user_id, [])

    def clear(self, user_id):
        self.data.pop(user_id, None)


sessions = SessionStore()


# -----------------------
# ГЛАВНАЯ ФУНКЦИЯ ОТВЕТА
# -----------------------
async def ask_ai(user_id: int, question: str) -> str:
    knowledge = search_knowledge(question)
    if not knowledge:
        knowledge = "нет совпадений"

    prompt = (
        f"Вопрос пользователя: {question}\n\n"
        f"Данные из базы:\n{knowledge}\n\n"
        "Если данных нет — попроси уточнить формулировку."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *sessions.get(user_id),
        {"role": "user", "content": prompt}
    ]

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
    )

    answer = response.choices[0].message.content
    sessions.add(user_id, "assistant", answer)
    return answer
