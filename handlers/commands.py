# handlers/commands.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("start"))
async def cmd_start(msg: Message):
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🆘 Помощь")]], resize_keyboard=True)
    await msg.answer(
        "<b>Добро пожаловать!</b>\nЯ — Dodo AI Assistant. Нажмите «🆘 Помощь» или просто напишите вопрос.",
        reply_markup=kb
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await cmd_start(msg)
