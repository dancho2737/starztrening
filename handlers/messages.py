import re
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from navigator.navigation_helper import (
    find_navigation_by_text,
    get_navigation,
)
from rule_checker.rules_helper import find_rule_by_text, get_rules
from ai_responder.responder import sessions, responder

router = Router()

# --- Клавиатуры ---
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆘 Помощь")],
            [KeyboardButton(text="📚 Навигация"), KeyboardButton(text="📜 Правила")],
        ],
        resize_keyboard=True,
    )

def help_keyboard() -> ReplyKeyboardMarkup:
    return main_keyboard()


# --- Паттерны для Да/Нет ---
YES_PATTERNS = re.compile(r"^(да|yes|ага|д|конечно|давайте|хочу)\b", flags=re.I)
NO_PATTERNS = re.compile(r"^(нет|не надо|не нужно|не)\b", flags=re.I)


# ==============================
#     ОБРАБОТЧИКИ КНОПОК
# ==============================

@router.message(lambda m: m.text == "🆘 Помощь")
async def on_help_button(message: Message):
    user_id = message.from_user.id
    sessions.set_state(user_id, "awaiting_question")
    sessions.append_history(user_id, "user", "clicked_help")

    await message.answer(
        "Привет! Я помогу вам разобраться с разделами сайта. Что вас интересует? "
        "Например: профиль, вывод средств, бонусы, верификация.",
        reply_markup=help_keyboard(),
    )


@router.message(lambda m: m.text == "📚 Навигация")
async def on_nav_list(message: Message):
    nav = get_navigation()

    text = "<b>Доступные разделы навигации:</b>\n\n"
    for name in nav.keys():
        text += f"🔹 <b>{name}</b>\n"

    text += "\nНапишите ключевое слово, и я подскажу путь."

    await message.answer(text, reply_markup=help_keyboard())


@router.message(lambda m: m.text == "📜 Правила")
async def on_rules_list(message: Message):
    rules = get_rules()

    text = "<b>Основные правила:</b>\n\n"
    for i, r in enumerate(rules, start=1):
        ans = r.get("answer", "")
        text += f"{i}. {ans[:100]}{'...' if len(ans) > 100 else ''}\n"
        if i >= 10:
            break

    text += "\nНапишите ключевое слово, чтобы получить полное правило."

    await message.answer(text, reply_markup=help_keyboard())


# ==============================
#       ГЛАВНЫЙ ОБРАБОТЧИК
# ==============================

@router.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    
    s = sessions.get(user_id)
    sessions.append_history(user_id, "user", text)

    state = s.get("state")

    # ------------------------------
    # Состояние: ждём ответ Да/Нет
    # ------------------------------
    if state == "awaiting_more":
        if NO_PATTERNS.match(text.lower()):
            sessions.set_state(user_id, "idle")
            sessions.append_history(user_id, "bot", "goodbye")
            await message.answer("Хорошо! Если потребуется помощь — просто нажмите кнопку «Помощь». 👋", 
                                 reply_markup=main_keyboard())
            return

        if YES_PATTERNS.match(text.lower()):
            sessions.set_state(user_id, "awaiting_question")
            await message.answer("Отлично! Сформулируйте ваш новый вопрос.", reply_markup=help_keyboard())
            return

        # если непонятно
        await message.answer(
            "Не совсем понял. Вы хотите задать ещё один вопрос? (Да/Нет)",
            reply_markup=help_keyboard()
        )
        return

    # ------------------------------
    # Основной поток поиска данных
    # ------------------------------

    nav_matches = find_navigation_by_text(text)
    rule_matches = find_rule_by_text(text)

    total_matches = len(nav_matches) + len(rule_matches)

    # --- если совпадений больше одного — просим уточнить ---
    if total_matches > 1:
        options = []

        for name, _ in nav_matches:
            options.append(f"• {name}")

        for r in rule_matches:
            kw = r.get("keywords", [])
            options.append(f"• {kw[0] if kw else 'правило'}")

        sessions.set_state(user_id, "awaiting_clarify")

        await message.answer(
            "Я нашёл несколько вариантов по вашему запросу. "
            "Уточните, пожалуйста, что именно вы имели в виду:\n\n" +
            "\n".join(options),
            reply_markup=help_keyboard()
        )
        return

    # --- если ничего не нашли — просим уточнить ---
    if total_matches == 0:
        nav = get_navigation()
        sample = ", ".join(list(nav.keys())[:6]) if nav else "профиль, вывод, верификация"

        sessions.set_state(user_id, "awaiting_clarify")

        await message.answer(
            f"Похоже, я не нашёл точного совпадения. Попробуйте уточнить вопрос.\n"
            f"Популярные запросы: {sample}",
            reply_markup=help_keyboard()
        )
        return

    # --- найдено ровно 1 совпадение ---
    if nav_matches:
        label, hint = nav_matches[0]
        source_text = hint
    else:
        rule = rule_matches[0]
        label = "Правило"
        source_text = rule.get("answer", "")

    final_source = f"Источник ({label}):\n{source_text}"

    # ------------------------------
    # Вызываем GPT через responder()
    # ------------------------------
    try:
        generated = await responder(
            user_id=user_id,
            source=final_source,
            question=text
        )
    except Exception as exc:
        generated = f"Не удалось сформировать ответ (ошибка сервиса): {exc}"

    # ------------------------------
    # Отправляем ответ
    # ------------------------------
    sessions.append_history(user_id, "bot", generated)

    await message.answer(generated, reply_markup=help_keyboard())

    # ------------------------------
    # Спрашиваем о дополнительных вопросах
    # ------------------------------
    sessions.set_state(user_id, "awaiting_more")

    await message.answer("Хотите задать дополнительный вопрос?", reply_markup=help_keyboard())
