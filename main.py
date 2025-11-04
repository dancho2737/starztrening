import json
import random
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from prompts import TRAINING_PROMPT
from openai import AsyncOpenAI

# === Настройки ===
BOT_TOKEN = "ТОКЕН_ТВОЕГО_БОТА"
PASSWORD = "123"
client = AsyncOpenAI(api_key="API_КЛЮЧ_OPENAI")

# === Хранилище пользователей (только в памяти) ===
authorized_users = set()
current_question = {}

# === Загрузка сценариев ===
with open("scenarios.json", "r", encoding="utf-8") as f:
    scenarios = json.load(f)


# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in authorized_users:
        await update.message.reply_text("Введите пароль для входа:")
        return

    question = random.choice(scenarios)
    current_question[user_id] = question

    await update.message.reply_text(f"Вопрос: {question['question']}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Проверка пароля
    if user_id not in authorized_users:
        if text == PASSWORD:
            authorized_users.add(user_id)
            await update.message.reply_text("✅ Пароль верный. Теперь введите /start для начала тренировки.")
        else:
            await update.message.reply_text("❌ Неверный пароль.")
        return

    # Проверка, есть ли активный вопрос
    if user_id not in current_question:
        await update.message.reply_text("Введите /start, чтобы начать тренировку.")
        return

    question = current_question[user_id]
    correct_answer = question["expected_answer"]

    # Отправляем в OpenAI для проверки
    prompt = f"""
Ты обучаешь сотрудников саппорта. 
Вопрос: {question['question']}
Ожидаемый ответ: {correct_answer}
Ответ пользователя: {text}

Проанализируй и выдай ответ строго в таком стиле:
❌ / ✅
Комментарий ИИ:
<оценка ответа>
Комментарий: <объяснение>
Рекомендация: <как улучшить>
Улучшенная формулировка: <пример идеального ответа>
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": TRAINING_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )

        ai_reply = response.choices[0].message.content.strip()
        await update.message.reply_text(ai_reply)

        # Следующий вопрос
        await asyncio.sleep(1)
        next_q = random.choice(scenarios)
        current_question[user_id] = next_q
        await update.message.reply_text(f"Следующий вопрос: {next_q['question']}")

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
