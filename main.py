import os
import json
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import openai
from prompts import TRAINING_PROMPT  # Берем промпт из prompts.py

# === CONFIG ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_KEY = os.environ.get("OPENAI_KEY")
openai.api_key = OPENAI_KEY

BOT_PASSWORD = "123"
RULES_FOLDER = "rules"
SCENARIO_FILE = "scenarios.json"

# === Загрузка правил ===
def load_rules():
    rules_data = {}
    if not os.path.exists(RULES_FOLDER):
        return rules_data
    for filename in os.listdir(RULES_FOLDER):
        if filename.endswith(".txt"):
            path = os.path.join(RULES_FOLDER, filename)
            with open(path, encoding="utf-8") as f:
                rules_data[filename] = f.read()
    return rules_data

RULES = load_rules()

# === Загрузка сценариев ===
def load_scenarios():
    if not os.path.exists(SCENARIO_FILE):
        return []
    with open(SCENARIO_FILE, encoding='utf-8') as f:
        data = json.load(f)
    random.shuffle(data)
    return data

SCENARIOS = load_scenarios()

# === Сессии пользователей ===
sessions = {}

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in sessions or not sessions[user_id].get("authenticated"):
        await update.message.reply_text("Введите пароль для доступа к боту:")
        sessions[user_id] = {"authenticated": False}
        return

    question = random.choice(SCENARIOS)
    sessions[user_id]["current_question"] = question
    await update.message.reply_text(f"Вопрос: {question['question']}")

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Проверка пароля
    if user_id not in sessions or not sessions[user_id].get("authenticated"):
        if text == BOT_PASSWORD:
            sessions[user_id]["authenticated"] = True
            await update.message.reply_text("✅ Пароль верный! Напишите /start для получения вопроса.")
        else:
            await update.message.reply_text("❌ Неверный пароль. Попробуйте ещё раз.")
        return

    # Проверка текущего вопроса
    current = sessions[user_id].get("current_question")
    if not current:
        await update.message.reply_text("Напишите /start чтобы получить вопрос.")
        return

    # Получаем правила по категории
    category = current.get("category", "")
    rules_text = RULES.get(category, "")

    # Формируем промпт для AI из prompts.py
    user_prompt = TRAINING_PROMPT.format(
        question=current["question"],
        expected_answer=current["expected_answer"]
    )
    if rules_text:
        user_prompt += f"\n\nПравила для оценки:\n{rules_text}"
    user_prompt += f"\n\nОтвет пользователя:\n{text}"

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты ассистент для оценки ответов. Давай выдавай оценку в формате:\n❌ Не совсем.\n\nКомментарий ИИ:\n<разбор>\n\nКомментарий:\n<совет>\n\nРекомендация:\n<рекомендация>\n\nУлучшенная формулировка:\n\"<правильный ответ>\""},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=400,
            temperature=0
        )
        ai_text = response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        ai_text = f"Ошибка AI: {e}"

    # Ответ пользователю
    await update.message.reply_text(f"{ai_text}")

    # Новый вопрос
    question = random.choice(SCENARIOS)
    sessions[user_id]["current_question"] = question
    await update.message.reply_text(f"Вопрос: {question['question']}")

# === Main ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
