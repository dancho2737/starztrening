# handlers/commands.py
from aiogram import Router, types
from aiogram.filters import Command

router = Router()

# /start
@router.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Привет! Я бот. Чем могу помочь?")

# /help
@router.message(Command("help"))
async def help_handler(message: types.Message):
    await message.answer("Вот список доступных команд:\n/start - начать\n/help - помощь")

# Можно добавить свои команды
@router.message(Command("settings"))
async def settings_handler(message: types.Message):
    await message.answer("Здесь можно изменить настройки бота.")
