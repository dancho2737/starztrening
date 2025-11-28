# handlers/commands.py
from aiogram import Router, F
from aiogram.types import Message

router = Router()

# Обработчик команды /start
@router.message(F.text == "/start")
async def start_command(message: Message):
    await message.answer("Привет! Я ваш бот. Чем могу помочь?")

# Пример другой команды /help
@router.message(F.text == "/help")
async def help_command(message: Message):
    await message.answer("Список доступных команд:\n/start - запуск бота\n/help - помощь")
