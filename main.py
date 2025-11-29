import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from handlers.commands import router as commands_router
from handlers.messages import router as messages_router

from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Подключаем все роутеры
dp.include_router(commands_router)
dp.include_router(messages_router)


async def main():
    print("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
