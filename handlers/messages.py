from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from ai_responder.responder import ask_ai, sessions, user_device

router = Router()

# --- Кнопки выбора устройства ---
device_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Смартфон"), KeyboardButton(text="💻 Компьютер")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


@router.message()
async def handle_message(msg: Message):
    user = msg.from_user.id
    text_raw = msg.text or ""
    text = text_raw.strip().lower()

    # --- Если пользователь ещё не выбрал устройство ---
    if user not in user_device:
        if text in ["смартфон", "📱 смартфон", "телефон", "mobile"]:
            user_device[user] = "mobile"
            return await msg.answer(
                "Отлично! 📱 Вы выбрали мобильную версию. Чем могу помочь?",
                reply_markup=None
            )

        if text in ["компьютер", "💻 компьютер", "пк", "desktop"]:
            user_device[user] = "desktop"
            return await msg.answer(
                "Отлично! 💻 Вы выбрали версию для компьютера. Что вас интересует?",
                reply_markup=None
            )

        # Первый контакт: просим выбрать устройство
        return await msg.answer(
            "Привет! 👋\n"
            "Перед началом请选择 устройство, с которого вы пользуетесь сервисом:\n\n"
            "📱 Смартфон\n💻 Компьютер",
            reply_markup=device_keyboard
        )

    # --- Устройство выбрано — продолжаем диалог с ИИ ---
    sessions.add(user, "user", text_raw)

    try:
        answer = await ask_ai(user, text_raw)
        await msg.answer(answer, reply_markup=None)
    except Exception as e:
        await msg.answer(
            "⚠️ Произошла ошибка при обработке запроса. Наши специалисты уже уведомлены.\n"
            f"Техническая информация: <code>{e}</code>"
        )
