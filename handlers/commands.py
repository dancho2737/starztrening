# handlers/commands.py
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

# Хендлер для команды /start
@router.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привет! Я бот на aiogram 3.x")

# Пример команды /help
@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "Список команд:\n"
        "/start - запуск бота\n"
        "/help - показать эту справку"
    )

# Можно добавить ещё команды по аналогии
# @router.message(Command("example"))
# async def example_handler(message: Message):
#     await message.answer("Это пример команды")
