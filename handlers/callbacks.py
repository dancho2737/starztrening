from aiogram import Router
from aiogram.types import CallbackQuery

router = Router()

@router.callback_query()
async def help_callbacks(call: CallbackQuery):
    data = call.data
    if data == "help_profile":
        text = "Главное меню → аватарка → Мой профиль → Личные данные."
    elif data == "help_security":
        text = "Настройки аккаунта → Безопасность → Смена пароля / 2FA."
    elif data == "help_transactions":
        text = "Настройки аккаунта → Транзакции → Депозит, Вывод, История."
    elif data == "help_games":
        text = "Слоты → Найдите свою игру → Поиск по названию или провайдеру."
    elif data == "help_bonus":
        text = "Кнопка Кешбэк, Промокоды → информация о бонусах."
    elif data == "help_language":
        text = "Настройки аккаунта → Изменить язык интерфейса."
    elif data == "help_support":
        text = "Контакты службы поддержки, правила использования сайта."
    else:
        text = "Выберите раздел из списка."

    # Обновляем текст сообщения с той же клавиатурой
    await call.message.edit_text(text, reply_markup=call.message.reply_markup)
    await call.answer()

