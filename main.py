# main.py
import asyncio
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

# Импорт роутеров
from handlers.commands import router as commands_router
from handlers.messages import router as messages_router

# Загружаем переменные окружения (для локальной работы, Heroku использует свои переменные)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в переменных окружения!")

# Создаём бота и диспетчер
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Подключаем роутеры
dp.include_router(commands_router)
dp.include_router(messages_router)

async def main():
    print("Бот запущен. Ожидание сообщений...")
    try:
        await dp.start_polling(bot)
    finally:
        # Корректное закрытие бота при остановке
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
