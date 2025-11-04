import logging
import os
import random
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler, ConversationHandler
)

import openai
from prompts import TRAINING_PROMPT  # промпт берётся из файла prompts.py

# === CONFIG ===

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_KEY = os.environ["OPENAI_KEY"]
openai.api_key = API_KEY

SCENARIO_FILE = "scenarios.json"
RULES_FOLDER = "rules"
BOT_PASSWORD = "starzbot"

# === STATES ===

PASSWORD_STATE, TRAINING, AWAITING_ANSWER = range(3)

# === LOGGER ===

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === SESSION ===

session = {}

# === Загрузка правил из папки rules ===

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
                key = os.path.splitext(filename)[0].lower()
                rules_data[key] = content
    logger.info(f"Загружено правил из {len(rules_data)} файлов из {RULES_FOLDER}")
    return rules_data

RULES = load_rules()

# === Загрузка сценариев ===

def load_scenarios():
    with open(SCENARIO_FILE, encoding='utf-8') as f:
        data = json.load(f)
    random.shuffle(data)
    return data

# === Оценка ответов ИИ ===

async def evaluate_answer(entry, user_answer, rules_text=""):
    question = entry["question"]
    expected_answer = entry["expected_answer"]

    prompt = TRAINING_PROMPT.format(question=question, expected_answer=expected_answer)
    prompt += f"\n\nПравила для оценки:\n{rules_text}"
    prompt += f"\n\nОтвет пользователя:\n{user_answer}"

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты — ассистент для оценки ответов."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0
        )
        content = response["choices"][0]["message"]["content"].strip()
        lower_eval = content.lower()
        if ("полностью верно" in lower_eval or "✅" in content or "верно" in lower_eval) and "неверно" not in lower_eval:
            evaluation_simple = "correct"
        else:
            evaluation_simple = "incorrect"

        return evaluation_simple, content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "error", "Ошибка при оценке ИИ. Попробуйте позже."

# === /auth ===

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔐 Введите пароль для доступа к боту:")
    return PASSWORD_STATE

async def password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id

    if password == BOT_PASSWORD:
        session[user_id] = {"authenticated": True, "step": 0}
        await update.message.reply_text("✅ Пароль принят! Напишите /start для начала тренировки.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Неверный пароль. Попробуйте /auth снова.")
        return ConversationHandler.END

# === /start - начало тренировки ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in session or not session[user_id].get("authenticated"):
        await update.message.reply_text("Сначала авторизуйтесь через /auth.")
        return ConversationHandler.END

    scenario = load_scenarios()
    session[user_id]["scenario"] = scenario
    session[user_id]["step"] = 0
    session[user_id]["score"] = {"correct": 0, "incorrect": 0}
    session[user_id]["last_answered"] = None  # для корректной команды /answer

    await ask_next(update)
    return AWAITING_ANSWER

# === Функция показа следующего вопроса с кнопкой "Дальше" ===

async def ask_next(update_obj):
    if isinstance(update_obj, Update):
        user_id = update_obj.effective_user.id
        send_func = update_obj.message.reply_text
    else:
        user_id = update_obj.from_user.id
        send_func = update_obj.message.reply_text

    step = session[user_id]["step"]
    scenario = session[user_id]["scenario"]

    if step >= len(scenario):
        await send_func("✅ Тренировка завершена. Введите /stop для просмотра статистики.")
        return ConversationHandler.END

    current = scenario[step]
    session[user_id]["current"] = current

    keyboard = [[InlineKeyboardButton("Дальше", callback_data="next")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_func(f"Вопрос: {current['question']}", reply_markup=reply_markup)

# === Обработка кнопки "Дальше" ===

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in session or "scenario" not in session[user_id]:
        await query.message.edit_text("Сначала напишите /start.")
        return

    session[user_id]["step"] += 1
    await ask_next(query)

# === Обработка ответа пользователя ===

async def process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in session or "current" not in session[user_id]:
        await update.message.reply_text("Сначала напишите /start.")
        return

    entry = session[user_id]["current"]
    category = entry.get("category", "").lower()
    rules_text = RULES.get(category, "")

    evaluation_simple, evaluation_text = await evaluate_answer(entry, text, rules_text)

    if evaluation_simple == "error":
        await update.message.reply_text(evaluation_text)
        return

    # Сохраняем последний отвеченный вопрос отдельно
    session[user_id]["last_answered"] = {
        "question": entry["question"],
        "answer": text,
        "evaluation": evaluation_simple,
        "correct_answer": entry["expected_answer"]
    }

    session[user_id]["score"].setdefault("correct", 0)
    session[user_id]["score"].setdefault("incorrect", 0)
    session[user_id]["score"][evaluation_simple] += 1

    if evaluation_simple == "correct":
        await update.message.reply_text(f"✅ Верно!\n\nКомментарий ИИ:\n{evaluation_text}")
        # Автоматически показать следующий вопрос
        session[user_id]["step"] += 1
        await ask_next(update)
    else:
        await update.message.reply_text(f"❌ Не совсем.\n\nКомментарий ИИ:\n{evaluation_text}")

# === /stop — показать статистику ===

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    score = session.get(user_id, {}).get("score", {"correct":0,"incorrect":0})
    msg = (f"📊 Статистика:\n"
           f"✅ Верных: {score.get('correct', 0)}\n"
           f"❌ Неверных: {score.get('incorrect', 0)}")
    await update.message.reply_text(msg)

# === /answer — показать последний правильный ответ ===

async def show_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    last = session.get(user_id, {}).get("last_answered")  # <-- теперь берём last_answered
    if not last:
        await update.message.reply_text("Нет ответа для показа.")
        return
    await update.message.reply_text(f"Правильный ответ:\n{last['correct_answer']}")

# === /help ===

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "/auth - авторизация\n"
        "/start - начать тренировку\n"
        "/stop - остановить тренировку и показать статистику\n"
        "/answer - показать правильный ответ на последний вопрос\n"
        "/help - показать это сообщение"
    )
    await update.message.reply_text(msg)

# === Главная точка запуска ===

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    auth_conv = ConversationHandler(
        entry_points=[CommandHandler('auth', auth)],
        states={
            PASSWORD_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_input)]
        },
        fallbacks=[]
    )

    application.add_handler(auth_conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("answer", show_correct))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process))
    application.add_handler(CallbackQueryHandler(next_question, pattern="next"))

    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
