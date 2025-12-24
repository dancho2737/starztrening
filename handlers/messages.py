from aiogram import Router
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from ai_responder.responder import ask_ai, sessions

router = Router()

# --- Reply-кнопки выбора устройства ---
device_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Смартфон"), KeyboardButton(text="💻 Компьютер")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


# -------------------- MESSAGE HANDLER --------------------
@router.message()
async def handle_message(msg: Message):
    user_id = msg.from_user.id
    text_raw = msg.text or ""
    text = text_raw.strip().lower()

    # --- если пользователь ещё не выбрал устройство ---
    if not sessions.has_device(user_id):
        # обработка кнопок
        if text in ("📱 смартфон", "смартфон", "телефон", "mobile"):
            sessions.set_device(user_id, "mobile")
            sessions.mark_seen(user_id)
            sessions.add_history(user_id, "assistant", "device_set_mobile")

            return await msg.answer(
                "Отлично 👌\n"
                "Вы используете **мобильную версию сайта**.\n\n"
                "Задайте вопрос — я подскажу, куда перейти и что сделать.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )

        if text in ("💻 компьютер", "компьютер", "пк", "desktop", "ноутбук"):
            sessions.set_device(user_id, "desktop")
            sessions.mark_seen(user_id)
            sessions.add_history(user_id, "assistant", "device_set_desktop")

            return await msg.answer(
                "Отлично 👌\n"
                "Вы используете **версию сайта для компьютера**.\n\n"
                "Задайте вопрос — я помогу разобраться.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )

        # первое приветствие
        sessions.mark_seen(user_id)
        sessions.add_history(user_id, "assistant", "greet_asked_device")

        return await msg.answer(
            "Здравствуйте! 👋\n\n"
            "Чтобы я подсказывал вам **точную навигацию**, выберите, "
            "с какого устройства вы пользуетесь сайтом:",
            reply_markup=device_keyboard
        )

    # --- устройство выбрано → обычная работа ---
    sessions.add(user_id, "user", text_raw)

    try:
        answer = await ask_ai(user_id, text_raw)

        # ответ с кнопками (inline)
        if isinstance(answer, dict):
            text_to_send = answer.get("text", "")
            buttons = answer.get("buttons", [])

            if buttons:
                markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=b.get("text", "?"),
                                callback_data=b.get("data", "")
                            )
                        ]
                        for b in buttons
                    ]
                )
                await msg.answer(text_to_send, reply_markup=markup)
            else:
                await msg.answer(text_to_send)
            return

        # обычный текст
        await msg.answer(str(answer))

    except Exception as e:
        await msg.answer(
            "⚠️ Произошла ошибка при обработке запроса.\n"
            f"Техническая информация: <code>{e}</code>",
            parse_mode="HTML",
        )


# -------------------- CALLBACK HANDLER --------------------
@router.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data or ""

    try:
        answer = await ask_ai(user_id, data)

        if isinstance(answer, dict):
            text_to_send = answer.get("text", "")
            buttons = answer.get("buttons", [])

            if buttons:
                markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=b.get("text", "?"),
                                callback_data=b.get("data", "")
                            )
                        ]
                        for b in buttons
                    ]
                )
                await callback.message.answer(text_to_send, reply_markup=markup)
            else:
                await callback.message.answer(text_to_send)
        else:
            await callback.message.answer(str(answer))

        await callback.answer()

    except Exception:
        await callback.answer("Ошибка обработки действия", show_alert=True)
