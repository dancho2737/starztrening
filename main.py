import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from bot.config import BOT_TOKEN
from handlers import commands, messages  # callbacks optional

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

dp.include_router(commands.router)
dp.include_router(messages.router)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Помощь"),
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
