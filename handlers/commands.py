from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

router = Router()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆘 Помощь")],
            [KeyboardButton(text="📚 Навигация"), KeyboardButton(text="📜 Правила")],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я помогу с навигацией по сайту и правилами. Нажми «Помощь», чтобы начать.",
        reply_markup=main_keyboard(),
    )
