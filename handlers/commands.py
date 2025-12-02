from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

router = Router()


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🆘 Помощь")]],
        resize_keyboard=True
    )


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я ваш помощник. Нажмите «🆘 Помощь», чтобы начать.",
        reply_markup=main_kb()
    )
