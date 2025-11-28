from aiogram import Router, types
from aiogram.filters import Command

router = Router()

# Пример команды /start
@router.message(Command("start"))
async def start_command_handler(message: types.Message):
    await message.answer("Привет! Я ваш бот.")

# Пример команды /help
@router.message(Command("help"))
async def help_command_handler(message: types.Message):
    await message.answer("Вот список команд, которые я понимаю:\n/start\n/help")
