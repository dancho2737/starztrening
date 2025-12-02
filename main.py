import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

from handlers import commands, messages, callbacks
from config import BOT_TOKEN

# Правильное создание бота для Aiogram 3.7+
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher()

# Регистрация всех хендлеров
dp.include_router(commands.router)
dp.include_router(messages.router)
dp.include_router(callbacks.router)

# Устанавливаем команды
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь")
    ])

async def main():
    await set_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
