import re
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from navigator.navigation_helper import (
    find_navigation_by_text,
    get_navigation,
)
from rule_checker.rules_helper import find_rule_by_text, get_rules
from ai_responder.responder import sessions, responder

router = Router()


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


YES_PATTERNS = re.compile(r"^(да|yes|ага|д|конечно|давайте|хочу)\b", flags=re.I)
NO_PATTERNS = re.compile(r"^(нет|не надо|не нужно|не)\b", flags=re.I)


# -------------------- КНОПКА ПОМОЩИ --------------------
@router.message(F.text == "🆘 Помощь")
async def on_help_button(message: Message):
    user_id = message.from_user.id
    sessions.set_state(user_id, "awaiting_question")
    sessions.append_history(user_id, "user", "clicked_help")
    await message.answer(
        "Привет! Чем могу помочь? Опиши, что ищешь (например: профиль, вывод средств, верификация).",
        reply_markup=help_keyboard(),
    )


# -------------------- КНОПКА НАВИГАЦИИ --------------------
@router.message(F.text == "📚 Навигация")
async def on_nav_list(message: Message):
    nav = get_navigation()
    text = "<b>Разделы сайта:</b>\n\n"
    for name in nav.keys():
        text += f"🔹 <b>{name}</b>\n"
    text += "\nНапиши ключевое слово или конкретный вопрос."
    await message.answer(text, reply_markup=help_keyboard())


# -------------------- КНОПКА ПРАВИЛ --------------------
@router.message(F.text == "📜 Правила")
async def on_rules_list(message: Message):
    rules = get_rules()
    text = "<b>Правила (кратко):</b>\n\n"
    for i, r in enumerate(rules, start=1):
        ans = r.get("answer", "")
        text += f"{i}. {ans[:120]}{'...' if len(ans) > 120 else ''}\n"
        if i >= 10:
            break
    text += "\nНапиши ключевое слово чтобы получить полное правило."
    await message.answer(text, reply_markup=help_keyboard())


# -------------------- ОБРАБОТКА ВСЕХ ТЕКСТОВ --------------------
@router.message(F.text)
async def on_text(message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    s = sessions.get(user_id)
    sessions.append_history(user_id, "user", text)

    # === Блок: Да/Нет ===
    if s.get("state") == "awaiting_more":
        if NO_PATTERNS.match(text.lower()):
            sessions.set_state(user_id, "idle")
            await message.answer("Хорошо, если понадоблюсь — обращайся. 👋", reply_markup=main_keyboard())
            sessions.append_history(user_id, "bot", "goodbye")
            return
        if YES_PATTERNS.match(text.lower()):
            sessions.set_state(user_id, "awaiting_question")
            await message.answer("Отлично! Что вас интересует дальше?", reply_markup=help_keyboard())
            return

        await message.answer("Не понял — вы хотите задать ещё вопрос? (Да/Нет)", reply_markup=help_keyboard())
        return

    # === Поиск в навигации и правилах ===
    nav_matches = find_navigation_by_text(text)
    rule_matches = find_rule_by_text(text)

    # === Если несколько совпадений → уточнение ===
    if len(nav_matches) + len(rule_matches) > 1:
        options = []
        for name, _ in nav_matches:
            options.append(name)
        for r in rule_matches:
            kw = r.get("keywords", [])
            options.append(kw[0] if kw else "правило")

        options_text = "\n".join(f"• {o}" for o in options)
        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            "Я нашёл несколько вариантов, уточните, пожалуйста:\n\n"
            f"{options_text}\n\n"
            "Напишите название раздела или ключевое слово.",
            reply_markup=help_keyboard(),
        )
        return

    # === Если не найдено ничего ===
    if not nav_matches and not rule_matches:
        nav = get_navigation()
        sample = ", ".join(list(nav.keys())[:6]) if nav else "профиль, вывод, верификация"
        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            f"Не нашёл точного совпадения. Можешь уточнить вопрос?\nПримеры: {sample}",
            reply_markup=help_keyboard(),
        )
        return

    # === Если найден один источник ===
    if nav_matches:
        label, source_text = nav_matches[0]
    else:
        rule = rule_matches[0]
        label = "Правило"
        source_text = rule.get("answer", "")

    final_source = f"Источник ({label}):\n{source_text}"

    # === Формируем ответ моделью ===
    try:
        generated = await responder.rephrase_from_source(final_source, text)
    except Exception as exc:
        generated = f"Не удалось сформировать ответ (ошибка сервиса): {exc}"

    # === Если модель просит уточнить ===
    if generated.lower().strip().startswith("нужно уточнить") or \
       ("уточн" in generated.lower() and len(generated) < 120):

        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            "Мне нужно немного больше информации. Уточни, пожалуйста, вопрос.",
            reply_markup=help_keyboard(),
        )
        return

    # === Отправляем ответ ===
    await message.answer(generated, reply_markup=help_keyboard())
    sessions.append_history(user_id, "bot", generated)

    # === Спрашиваем про дополнительные вопросы ===
    sessions.set_state(user_id, "awaiting_more")
    await message.answer("Есть ли дополнительные вопросы?", reply_markup=help_keyboard())
