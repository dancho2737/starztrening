from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()


@router.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "<b>Добро пожаловать!</b> 👋\n\n"
        "Я — ваш персональный помощник.\n"
        "Просто отправьте сообщение, и я постараюсь помочь — "
        "от ответов на вопросы до подсказок по любым темам."
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "<b>Доступные команды:</b>\n"
        "• /start — начать работу с ботом\n"
        "• /help — справка\n\n"
        "Я понимаю обычный текст — просто напишите ваш вопрос."
    )
