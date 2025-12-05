from aiogram import Router
from aiogram.types import Message
from bot.config import OPENAI_API_KEY, OPENAI_MODEL
from openai import OpenAI

import json
from pathlib import Path

router = Router()
client = OpenAI(api_key=OPENAI_API_KEY)

# ====================================
# ЗАГРУЗКА ВСЕХ ФАЙЛОВ
# ====================================

BASE_DIR = Path(__file__).resolve().parents[1] / "ai_responder"

DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = BASE_DIR / "prompts"

# navigation.json
try:
    navigation = json.loads((DATA_DIR / "navigation.json").read_text(encoding="utf-8"))
except Exception:
    navigation = []

# rules.json
try:
    rules = json.loads((DATA_DIR / "rules.json").read_text(encoding="utf-8"))
except Exception:
    rules = []

# system_prompt.txt
try:
    SYSTEM_PROMPT = (PROMPTS_DIR / "system_prompt.txt").read_text(encoding="utf-8")
except Exception:
    SYSTEM_PROMPT = "Ты — оператор поддержки. Отвечай кратко и по делу."


# ====================================
# ПОИСК ЗНАНИЙ В navigation + rules
# ====================================

def search_knowledge(question: str):
    q = question.lower()
    found = []

    # NAVIGATION
    for item in navigation:
        for kw in item.get("keywords", []):
            if kw.lower() in q:
                found.append(f"{item['hint']}")
                break

    # RULES
    for rule in rules:
        for kw in rule.get("keywords", []):
            if kw.lower() in q:
                found.append(rule.get("answer", ""))
                break

    return "\n\n".join(found)


# ====================================
# ОБРАБОТКА СООБЩЕНИЙ
# ====================================

@router.message()
async def handle_message(msg: Message):
    user_text = msg.text.strip()

    if not user_text:
        return await msg.answer("Пожалуйста, отправьте текст.")

    try:
        # Найти данные по вопросу
        knowledge = search_knowledge(user_text)

        final_input = (
            f"Вопрос пользователя: {user_text}\n"
            f"Найденные данные:\n{knowledge if knowledge else 'нет совпадений'}"
        )

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": final_input},
            ],
            temperature=0.2,
        )

        ai_answer = response.choices[0].message.content.strip()

        await msg.answer(ai_answer)

    except Exception as e:
        await msg.answer(
            "⚠ Ошибка при генерации ответа.\n"
            f"<code>{e}</code>"
        )
