from aiogram import Router
from aiogram.types import Message
from bot.config import OPENAI_API_KEY, OPENAI_MODEL
from openai import OpenAI

import json
from pathlib import Path

router = Router()
client = OpenAI(api_key=OPENAI_API_KEY)

# ============================
# ЗАГРУЗКА ФАЙЛОВ
# ============================

BASE_DIR = Path("ai_responder/data")

try:
    navigation = json.loads((BASE_DIR / "navigation.json").read_text(encoding="utf-8"))
except:
    navigation = []

try:
    rules = json.loads((BASE_DIR / "rules.json").read_text(encoding="utf-8"))
except:
    rules = []


# ============================
# ПОИСК ЗНАНИЙ
# ============================

def search_knowledge(question: str):
    q = question.lower()
    found = []

    # NAVIGATION
    for item in navigation:
        for kw in item.get("keywords", []):
            if kw.lower() in q:
                found.append(f"🔹 {item['name']}:\n{item['hint']}")
                break

    # RULES
    for rule in rules:
        for kw in rule.get("keywords", []):
            if kw.lower() in q:
                found.append(rule.get("answer", ""))
                break

    return "\n\n".join(found)


# ============================
# SYSTEM PROMPT
# ============================

SYSTEM_PROMPT = (
    "Ты — дружелюбный оператор поддержки казино. "
    "Отвечай простым и живым языком. "
    "Используй только данные из базы, не придумывай. "
    "Если нужной информации нет — попроси пользователя уточнить."
)


# ============================
# AI ОБРАБОТКА СООБЩЕНИЙ
# ============================

@router.message()
async def handle_message(msg: Message):
    user_text = msg.text.strip()

    if not user_text:
        return await msg.answer("Пожалуйста, отправьте текст.")

    try:
        knowledge = search_knowledge(user_text)

        final_input = (
            f"Вопрос пользователя: {user_text}\n"
            f"Данные из базы:\n{knowledge if knowledge else 'нет совпадений'}"
        )

        # ❗ Используем правильный API
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": final_input}
            ],
            temperature=1,
        )

        ai_answer = response.choices[0].message["content"]

        await msg.answer(ai_answer)

    except Exception as e:
        await msg.answer(
            "⚠️ <b>Произошла ошибка при генерации ответа.</b>\n"
            f"Техническая информация: <code>{e}</code>"
        )
