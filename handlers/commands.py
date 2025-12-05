from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "<b>Добро пожаловать!</b>\n"
        "Я — Dodo AI Assistant. Напишите ваш вопрос обычной фразой, например: 'Как зайти в профиль?'"
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "<b>Помощь</b>\n"
        "Просто опишите, что вы хотите найти на сайте — бот ответит по базе данных (навигация/правила)."
    )
