from aiogram import Router
from aiogram.types import Message
from bot.config import OPENAI_API_KEY, OPENAI_MODEL
from openai import OpenAI
import json
import os

router = Router()
client = OpenAI(api_key=OPENAI_API_KEY)


# -------------------------------
# Загружаем данные из data/*
# -------------------------------
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

def load_json(path):
    try:
        with open(os.path.join(BASE_DIR, "data", path), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

navigation = load_json("navigation.json")
rules = load_json("rules.json")


# -------------------------------
# Формирование системного контекста
# -------------------------------
def build_system_prompt():
    text = "Ты — помощник сайта. Отвечай строго по данным.\n\n"

    if rules:
        text += "Правила:\n"
        for r in rules:
            text += f"- {r}\n"

    if navigation:
        text += "\nНавигация сайта:\n"
        for k, v in navigation.items():
            text += f"- {k}: {v}\n"

    return text


SYSTEM_PROMPT = build_system_prompt()


# -------------------------------
# Обработка сообщений
# -------------------------------
@router.message()
async def handle_message(msg: Message):
    user_text = msg.text.strip()

    if not user_text:
        return await msg.answer("Пожалуйста, отправьте текстовое сообщение.")

    try:
        # Новый Responses API (это важно!)
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ]
        )

        # Правильный способ достать текст
        ai_answer = response.output_text or "Не удалось получить ответ."

        await msg.answer(ai_answer)

    except Exception as e:
        await msg.answer(
            "⚠️ <b>Ошибка генерации ответа.</b>\n"
            f"Техническая информация: <code>{e}</code>"
        )
