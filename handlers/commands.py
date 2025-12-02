from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def start_cmd(msg: types.Message):
    await msg.answer(
        "👋 Привет! Я — помощник.\n\n"
        "Нажми кнопку <b>Помощь</b> или просто напиши вопрос.",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Помощь")]],
            resize_keyboard=True
        )
    )

@router.message(Command("help"))
async def help_cmd(msg: types.Message):
    await msg.answer(
        "Напиши любой вопрос, и я помогу 😊",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Помощь")]],
            resize_keyboard=True
        )
    )
