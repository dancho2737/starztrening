# handlers/commands.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ai_responder.responder import user_device

router = Router()

@router.message(Command("start"))
async def cmd_start(msg: Message):
    user = msg.from_user.id

    # Если пользователь перезапустил бота — сбрасываем устройство
    if user in user_device:
        del user_device[user]

    await msg.answer(
        "<b>Добро пожаловать!</b> 😊\n"
        "Я — Dodo AI Assistant.\n\n"
        "Перед началом подскажите, с какого устройства вы пользуетесь:\n"
        "📱 <b>Смартфон</b>\n💻 <b>Компьютер</b>\n\n"
        "Напишите: «Смартфон» или «Компьютер»."
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "Я могу помочь по вопросам сайта.\n"
        "Пожалуйста, задайте ваш вопрос!"
    )
