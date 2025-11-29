import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from handlers.commands import router as commands_router
from handlers.messages import router as messages_router

import os

# Читаем токены из переменных окружения Heroku
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")  # если будешь использовать в AI-ответах

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Подключаем роутеры
dp.include_router(commands_router)
dp.include_router(messages_router)

async def main():
    print("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
