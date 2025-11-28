from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

@router.message(commands=["start"])
async def start(message: Message):
    await message.answer(
        "Привет! Я Dodo AI Assistant.\n"
        "Задайте мне вопрос обычной фразой, например:\n"
        "- 'Как пополнить баланс?'\n"
        "- 'Можно ли использовать два аккаунта?'\n"
        "Я дам вам понятный ответ и подскажу, где найти информацию."
    )

@router.message(commands=["help"])
async def help_command(message: Message):
    # Кнопки для подсказки по темам
    help_keyboard = InlineKeyboardMarkup(row_width=2)
    help_keyboard.add(
        InlineKeyboardButton(text="Баланс и Профиль", callback_data="help_profile"),
        InlineKeyboardButton(text="Безопасность", callback_data="help_security"),
        InlineKeyboardButton(text="Транзакции", callback_data="help_transactions"),
        InlineKeyboardButton(text="Игры", callback_data="help_games"),
        InlineKeyboardButton(text="Бонусы", callback_data="help_bonus"),
        InlineKeyboardButton(text="Язык", callback_data="help_language"),
        InlineKeyboardButton(text="Поддержка", callback_data="help_support"),
    )

    await message.answer(
        "Выберите раздел, чтобы получить подсказку или инструкцию:",
        reply_markup=help_keyboard
    )

@router.message(commands=["support"])
async def support_command(message: Message):
    await message.answer(
        "Контакты службы поддержки:\n"
        "- Email: support@dodobet.com\n"
        "- Онлайн-чат на сайте\n"
        "- Правила сайта: /help → Поддержка"
    )

