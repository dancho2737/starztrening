import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from bot.config import BOT_TOKEN
from handlers import commands, messages, callbacks

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

def register_handlers():
    dp.include_router(commands.router)
    dp.include_router(messages.router)
    dp.include_router(callbacks.router)

async def on_startup():
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="help", description="Помощь"),
        ]
    )

async def main():
    register_handlers()
    await on_startup()
    # Long polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
