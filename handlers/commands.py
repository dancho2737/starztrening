from aiogram import Router
from aiogram.types import Message

router = Router()

# Обработчик команды /start
@router.message()
async def start_handler(message: Message):
    if message.text == "/start":
        await message.answer("Привет! Я бот на aiogram 3.x. Как дела?")

# Обработчик команды /help
@router.message()
async def help_handler(message: Message):
    if message.text == "/help":
        await message.answer("Список доступных команд:\n/start - Запуск бота\n/help - Помощь")

# Можно добавить другие команды
@router.message()
async def echo_handler(message: Message):
    # Просто повторяет сообщение пользователя
    if message.text.startswith("/"):
        return  # Игнорируем другие команды
    await message.answer(f"Вы написали: {message.text}")
