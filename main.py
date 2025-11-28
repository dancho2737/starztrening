import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.filters import Command
from handlers import commands, messages, callbacks  # Подключаем наши хендлеры
from config import BOT_TOKEN  # Твой токен из .env

# Создаём бота и диспетчер
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Регистрируем обработчики
dp.include_router(commands.router)
dp.include_router(messages.router)
dp.include_router(callbacks.router)

# Настройка команд в интерфейсе Telegram
async def set_bot_commands():
    commands_list = [
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Справка по боту"),
        BotCommand(command="support", description="Контакты службы поддержки"),
    ]
    await bot.set_my_commands(commands_list)

# Основной запуск
async def main():
    # Устанавливаем команды
    await set_bot_commands()

    # Запуск бота
    print("Бот запущен...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())

