import re
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Text

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


@router.message(Text(equals="🆘 Помощь"))
async def on_help_button(message: Message):
    user_id = message.from_user.id
    sessions.set_state(user_id, "awaiting_question")
    sessions.append_history(user_id, "user", "clicked_help")
    await message.answer(
        "Привет! Чем могу помочь? Опиши, что ищешь (например: профиль, вывод средств, верификация).",
        reply_markup=help_keyboard(),
    )


@router.message(Text(equals="📚 Навигация"))
async def on_nav_list(message: Message):
    nav = get_navigation()
    text = "<b>Разделы сайта:</b>\n\n"
    for name in nav.keys():
        text += f"🔹 <b>{name}</b>\n"
    text += "\nНапиши ключевое слово или конкретный вопрос."
    await message.answer(text, reply_markup=help_keyboard())


@router.message(Text(equals="📜 Правила"))
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


@router.message()
async def on_text(message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    s = sessions.get(user_id)
    sessions.append_history(user_id, "user", text)

    # If we are awaiting yes/no after answering
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
        # если непонятно — спросим уточнение
        await message.answer("Не понял — вы хотите задать ещё вопрос? (Да/Нет)", reply_markup=help_keyboard())
        return

    # Основной поток: ищем по navigation и rules
    nav_matches = find_navigation_by_text(text)
    rule_matches = find_rule_by_text(text)

    # Если нашлось более одного совпадения — просим уточнить
    if len(nav_matches) + len(rule_matches) > 1:
        # Предложим варианты
        options = []
        for name, _ in nav_matches:
            options.append(name)
        for r in rule_matches:
            # у правил может не быть заголовка — возьмём первые keywords
            kw = r.get("keywords", [])
            options.append(kw[0] if kw else "правило")
        options_text = "\n".join(f"• {o}" for o in options)
        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            "Я нашёл несколько вариантов, уточните, пожалуйста, что именно вы имеете в виду:\n\n"
            f"{options_text}\n\n"
            "Напишите название раздела или ключевое слово из списка.",
            reply_markup=help_keyboard(),
        )
        return

    # Если ничего не найдено — просим уточнить или предложим подсказки
    if not nav_matches and not rule_matches:
        # Показываем варианты популярных разделов из data
        nav = get_navigation()
        sample = ", ".join(list(nav.keys())[:6]) if nav else "профиль, вывод, верификация"
        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            "Не нашёл точного совпадения. Можешь уточнить вопрос? "
            f"Примеры запросов: {sample}",
            reply_markup=help_keyboard(),
        )
        return

    # Если найден ровно один результат (либо из navigation, либо из rules)
    source_text = ""
    label = ""
    if nav_matches:
        label, hint = nav_matches[0]
        source_text = hint
    else:
        rule = rule_matches[0]
        label = "Правило"
        source_text = rule.get("answer", "")

    # Переформулируем через OpenAI
    # Добавим в prompt короткую заметку, что источник (label) и текст source_text — единственный источник
    final_source = f"Источник ({label}):\n{source_text}"
    try:
        generated = await responder.rephrase_from_source(final_source, text)
    except Exception as exc:
        generated = f"Не удалось сформировать ответ (ошибка сервиса): {exc}"

    # Если модель вернула указание "Нужно уточнить" или «UNSURE» — попросим уточнение
    if generated.lower().strip().startswith("нужно уточнить") or "уточн" in generated.lower() and len(generated) < 120:
        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            "Мне нужно немного больше информации, чтобы точно ответить. Можете уточнить ваш вопрос? Например: где именно вы нажимали, что видите на экране и т.п.",
            reply_markup=help_keyboard(),
        )
        return

    # Отправляем сформулированный ответ
    await message.answer(generated, reply_markup=help_keyboard())
    sessions.append_history(user_id, "bot", generated)

    # После ответа — спрашиваем про дополнительные вопросы
    sessions.set_state(user_id, "awaiting_more")
    await message.answer("Есть ли дополнительные вопросы?", reply_markup=help_keyboard())
