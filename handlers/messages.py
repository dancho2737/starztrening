from aiogram import Router
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from ai_responder.responder import ask_ai, sessions, user_device

router = Router()

# --- Кнопки выбора устройства (reply keyboard для мобильных клиентов) ---
device_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 Смартфон"), KeyboardButton(text="💻 Компьютер")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


@router.message()
async def handle_message(msg: Message):
    user = msg.from_user.id
    text_raw = msg.text or ""
    text = text_raw.strip().lower()

    # --- Если пользователь ещё не выбрал устройство ---
    if user not in user_device:
        # 1) Пользователь ввёл слово выбора устройства (текстом)
        if text in ["смартфон", "📱 смартфон", "телефон", "mobile"]:
            # Сохраняем состояние и помечаем, что пользователь уже видел приветствие
            user_device[user] = "mobile"
            sessions.set_device(user, "mobile")
            sessions.mark_seen(user)
            sessions.add_history(user, "assistant", "device_set_mobile")

            # Убираем клавиатуру и подтверждаем выбор
            return await msg.answer(
                "Отлично! 📱 Навигация переключена на мобильную версию. Чем могу помочь?",
                reply_markup=ReplyKeyboardRemove()
            )

        if text in ["компьютер", "💻 компьютер", "пк", "desktop"]:
            user_device[user] = "desktop"
            sessions.set_device(user, "desktop")
            sessions.mark_seen(user)
            sessions.add_history(user, "assistant", "device_set_desktop")

            return await msg.answer(
                "Отлично! 💻 Навигация переключена на версию для компьютера. Что вас интересует?",
                reply_markup=ReplyKeyboardRemove()
            )

        # 2) Первый контакт: просим выбрать устройство и помечаем приветствие как отправленное
        #    (это предотвращает дублирование приветствия из responder.ask_ai)
        sessions.mark_seen(user)
        sessions.add_history(user, "assistant", "greet_asked_device")

        return await msg.answer(
            "Здравствуйте. Прежде чем начать, пожалуйста, выберите, с какого устройства вы пользуетесь сервисом:\n\n"
            "📱 Смартфон\n💻 Компьютер\n\n"
            "Нажмите соответствующую кнопку или введите слово «Смартфон» / «Компьютер».",
            reply_markup=device_keyboard,
        )

    # --- Устройство уже выбрано — продолжаем диалог с ИИ ---
    # Сохраняем оригинальный текст в истории (без lower())
    sessions.add(user, "user", text_raw)

    try:
        answer = await ask_ai(user, text_raw)

        # Если ask_ai вернул структуру с кнопками — отрисуем Inline-кнопки (callback_data)
        if isinstance(answer, dict):
            text_to_send = answer.get("text") or ""
            buttons = answer.get("buttons") or []
            if buttons:
                markup = InlineKeyboardMarkup(row_width=2)
                for b in buttons:
                    # ожидаем структуру {"text": "...", "data": "device:mobile"}
                    btn_text = b.get("text") or "?"
                    btn_data = b.get("data") or btn_text
                    markup.add(InlineKeyboardButton(text=btn_text, callback_data=btn_data))
                await msg.answer(text_to_send, reply_markup=markup)
            else:
                # словарь без кнопок — просто отправляем текст
                await msg.answer(text_to_send)
            return

        # обычная строка-ответ
        await msg.answer(str(answer))

    except Exception as e:
        await msg.answer(
            "⚠️ Произошла ошибка при обработке запроса. Наши специалисты уведомлены.\n"
            f"Техническая информация: <code>{e}</code>",
            parse_mode="HTML",
        )
