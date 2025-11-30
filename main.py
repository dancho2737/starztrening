import asyncio
from aiogram import Bot, Dispatcher
from bot.config import TOKEN

from handlers.commands import router as commands_router
from handlers.messages import router as messages_router

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Подключаем хендлеры
    dp.include_router(commands_router)
    dp.include_router(messages_router)

    # Запуск
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
