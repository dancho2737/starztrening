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

# -------------------- LIVE SUPPORT / Com100 --------------------
# Поставь здесь ссылку на ваш Com100/страницу живой поддержки:
LIVE_SUPPORT_URL = "https://cutt.ly/atghzvA0"

# Сколько подряд "провалов" считать триггером для предложения живой поддержки
MAX_FAILS_BEFORE_SUPPORT = 3

# Временное хранение счётчиков неудачных ответов по user_id
_failed_answers = {}  # user_id -> int

def build_live_support_markup() -> InlineKeyboardMarkup:
    """
    Кнопка с ссылкой на Com100.
    Текст кнопки: "Написать живой поддержке"
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Написать живой поддержке",
                    url=LIVE_SUPPORT_URL
                )
            ]
        ]
    )
# ---------------------------------------------------------------


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

    # --- ключевое слово: "помощь оператора" ---
    if "помощь оператора" in text:
        await msg.answer(
            "Чтобы связаться с живой поддержкой, нажмите на кнопку ниже",
            reply_markup=build_live_support_markup()
        )
        # не считаем это попыткой AI — сразу отдадим пользователю ссылку
        return

    # --- если пользователь ещё не выбрал устройство ---
    if not sessions.has_device(user_id):
        # обработка кнопок
        if text in ("📱 смартфон", "смартфон", "телефон", "mobile"):
            sessions.set_device(user_id, "mobile")
            sessions.mark_seen(user_id)
            sessions.add_history(user_id, "assistant", "device_set_mobile")

            return await msg.answer(
                "Отлично 👌\n"
                "Вы используете 📱 мобильную версию сайта.\n\n"
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
                "Вы используете версию сайта для компьютера 💻.\n\n"
                "Задайте вопрос — я помогу разобраться.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )

        # первое приветствие
        sessions.mark_seen(user_id)
        sessions.add_history(user_id, "assistant", "greet_asked_device")

        return await msg.answer(
            "Здравствуйте! 👋\n\n"
            "Чтобы я подсказывал вам точную навигацию, выберите, "
            "с какого устройства вы пользуетесь сайтом:",
            reply_markup=device_keyboard
        )

    # --- устройство выбрано → обычная работа ---
    sessions.add(user_id, "user", text_raw)

    try:
        answer = await ask_ai(user_id, text_raw)

        # --- определим, считать ли это "провалом" ответа AI ---
        failed = False
        # если нет ответа
        if answer is None:
            failed = True
        else:
            if isinstance(answer, dict):
                text_to_check = (answer.get("text", "") or "").strip().lower()
                if not text_to_check:
                    failed = True
            else:
                text_to_check = str(answer).strip().lower()
                if not text_to_check:
                    failed = True

        # дополнительно: если AI вернул очевидную фразу отказа/фоллбека — считаем провалом
        if not failed:
            fallback_phrases = [
                "не могу", "не смог", "не нашел", "не нашёл", "не понимаю",
                "не найдено", "не удалось найти", "извините, я не могу", "не могу помочь"
            ]
            t = text_to_check
            for p in fallback_phrases:
                if p in t:
                    failed = True
                    break

        # если провал — увеличиваем счётчик, иначе сбрасываем
        if failed:
            _failed_answers[user_id] = _failed_answers.get(user_id, 0) + 1
        else:
            _failed_answers[user_id] = 0

        # если достигнут порог — предложить живую поддержку и сбросить счётчик
        if _failed_answers.get(user_id, 0) >= MAX_FAILS_BEFORE_SUPPORT:
            _failed_answers[user_id] = 0  # сброс
            await msg.answer(
                "❗ Если я не могу помочь вам с этим вопросом, "
                "вы можете обратиться к живой поддержке.\n\n"
                "Нажмите кнопку ниже, чтобы связаться с оператором.",
                reply_markup=build_live_support_markup()
            )
            return

        # --- ответ с кнопками (inline)
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
