from aiogram import Router
from aiogram.types import Message
import json

router = Router()

# Загружаем базу данных
with open("data/navigation.json", encoding="utf-8") as f:
    navigation = json.load(f)

with open("data/rules.json", encoding="utf-8") as f:
    rules = json.load(f)

def find_answer(user_text):
    user_text_lower = user_text.lower()
    
    # Сначала ищем в навигации
    for key, value in navigation.items():
        if any(kw.lower() in user_text_lower for kw in value["keywords"]):
            return value["hint"]
    
    # Потом ищем в правилах
    for item in rules:
        if any(kw.lower() in user_text_lower for kw in item["keywords"]):
            return item["answer"]
    
    return "Извините, я не знаю ответ на этот вопрос. Попробуйте переформулировать."

@router.message()
async def handle_message(message: Message):
    answer = find_answer(message.text)
    await message.answer(answer)

