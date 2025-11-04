import os
import json
import random
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import openai
from prompts import TRAINING_PROMPT  # промпт берётся из prompts.py

# === CONFIG ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_KEY = os.environ["OPENAI_KEY"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1003240182749")  # твой канал
SCENARIO_FILE = "scenarios.json"
RULES_FOLDER = "rules"

openai.api_key = OPENAI_KEY

# === LOGGER ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Сессии пользователей ===
sessions = {}

# === Загрузка правил ===
def load_rules():
    rules_data = {}
    if not os.path.exists(RULES_FOLDER):
        logger.warning(f"Папка с правилами {RULES_FOLDER} не найдена")
        return rules_data
    for filename in os.listdir(RULES_FOLDER):
        if filename.endswith(".txt"):
            path = os.path.join(RULES_FOLDER, filename)
            with open(path, encoding="utf-8") as f:
                content = f.read()
                rules_data[filename] = content
    logger.info(f"Загружено правил из {len(rules_data)} файлов из {RULES_FOLDER}")
    return rules_data

RULES = load_rules()

# === Загрузка сценариев ===
def load_scenarios():
    with open(SCENARIO_FILE, encoding='utf-8') as f:
        data = json.load(f)
    random.shuffle(data)
    return data

SCENARIOS = load_scenarios()

# === Выдача следующего вопроса ===
async def ask_question(user_id, username, context: ContextTypes.DEFAULT_TYPE):
    question = random.choice(SCENARIOS)
    sessions.setdefault(user_id, {})
    sessions[user_id]["current_question"] = question

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"Вопрос: {question['question']}"
    )

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return

    user = update.message.from_user
    if user is None:
        return

    user_id = user.id
    username = user.username or user.first_name
    text = update.message.text.strip()

    # Новый вопрос
    if text.lower() == "!вопрос":
        await ask_question(user_id, username, context)
        return

    # Ответ пользователя
    if text.startswith("!"):
        if user_id not in sessions or "current_question" not in sessions[user_id]:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"@{username}, сначала напишите !вопрос чтобы получить вопрос."
            )
            return

        user_answer = text[1:].strip()
        current = sessions[user_id]["current_question"]
        category = current.get("category", "")
        rules_text = RULES.get(category, "")

        prompt = TRAINING_PROMPT.format(
            question=current["question"],
            expected_answer=current["expected_answer"]
        )
        if rules_text:
            prompt += f"\n\nПравила для оценки:\n{rules_text}"
        prompt += f"\n\nОтвет пользователя:\n{user_answer}"

        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты ассистент для оценки ответов. Формат ответа:\n❌ Не совсем.\n\nКомментарий ИИ:\n<разбор>\n\nКомментарий:\n<совет>\n\nРекомендация:\n<рекомендация>\n\nУлучшенная формулировка:\n\"<правильный ответ>\""},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0
            )
            ai_text = response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            ai_text = f"Ошибка AI: {e}"

        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"Ответ от @{username}:\n{user_answer}\n\n{ai_text}"
        )

        # Следующий вопрос
        await ask_question(user_id, username, context)

# === Главная точка запуска ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен для канала...")
    app.run_polling()

if __name__ == "__main__":
    main()
