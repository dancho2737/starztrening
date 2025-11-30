from aiogram import Router
from aiogram.types import Message

router = Router()

@router.message()
async def message_handler(message: Message):
    user_text = message.text

    # Имитация “человеческого” оператора
    if len(user_text) < 3:
        await message.answer("Я правильно понял, что вы имеете в виду? Можете уточнить?")
        return

    await message.answer(f"Понял вас 👍\n\n{user_text}\n\nСейчас объясню…")
