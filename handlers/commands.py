from aiogram import Router, types

router = Router()


@router.message(commands=["start"])
async def start_cmd(message: types.Message):
    await message.answer("Здравствуйте! Я ваш AI оператор поддержки. Чем могу помочь?")
