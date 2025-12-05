# handlers/commands.py
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "<b>Добро пожаловать!</b>\n"
        "Нажмите /help чтобы получить подсказки. Просто отправьте вопрос в чат — я помогу."
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "<b>Помощь</b>\n"
        "Напишите свой вопрос обычной фразой, например:\n"
        "— Как зайти в профиль?\n"
        "— Где вывод средств?\n\n"
        "Я отвечаю только по информации, которая есть в базе (navigation.json и rules.json)."
    )
