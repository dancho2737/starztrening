import re
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from navigator.navigation_helper import find_navigation_by_text, get_navigation
from rule_checker.rules_helper import find_rule_by_text
from ai_responder.responder import sessions, ask_model

from bot.config import OPENAI_MODEL

router = Router()

# клавиатура — только одна кнопка Помощь
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🆘 Помощь")]],
        resize_keyboard=True
    )

YES = re.compile(r"^(да|yes|ага|конечно)\b", flags=re.I)
NO = re.compile(r"^(нет|не|no)\b", flags=re.I)


SYSTEM_PROMPT = (
    "Ты — дружелюбный и внимательный помощник. Отвечай по-русски, коротко и понятно. "
    "В ответах используй ТОЛЬКО информацию, предоставленную в SOURCE. "
    "Если SOURCE не покрывает вопрос — попроси уточнить. "
    "Если нужно перечислить шаги, делай их пронумерованными. "
    "Всегда завершай ответ коротким вопросом: 'Есть ли ещё вопросы?'"
)


@router.message(lambda m: m.text == "🆘 Помощь")
async def on_help(message: Message):
    user_id = message.from_user.id
    sessions.set_state(user_id, "awaiting_question")
    sessions.append_history(user_id, "system", "user opened help")
    await message.answer(
        "Привет! Чем могу помочь? Опиши коротко свой вопрос (например: 'где вывод', 'профиль').",
        reply_markup=main_keyboard()
    )


@router.message()
async def handle_all(message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    s = sessions.get(user_id)
    sessions.append_history(user_id, "user", text)

    state = s.get("state", "idle")

    # Если ожидаем подтверждение после ответа
    if state == "awaiting_more":
        if NO.match(text):
            sessions.set_state(user_id, "idle")
            sessions.append_history(user_id, "assistant", "goodbye")
            await message.answer("Спасибо! Обращайтесь, если что — нажмите «Помощь».", reply_markup=main_keyboard())
            return
        if YES.match(text):
            sessions.set_state(user_id, "awaiting_question")
            await message.answer("Окей. Задайте следующий вопрос.", reply_markup=main_keyboard())
            return
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.", reply_markup=main_keyboard())
        return

    # Поиск в данных
    nav_matches = find_navigation_by_text(text)
    rule_matches = find_rule_by_text(text)

    total = len(nav_matches) + len(rule_matches)

    if total == 0:
        # не нашлось — даём дружелюбный follow-up и подсказки
        nav = get_navigation()
        sample = ", ".join(list(nav.keys())[:6]) if nav else "профиль, вывод, верификация"
        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            f"Извините, я не уверен, что понял. Можете уточнить запрос? Примеры: {sample}",
            reply_markup=main_keyboard()
        )
        return

    if total > 1:
        # несколько совпадений — предложим варианты
        options = []
        for name, _ in nav_matches:
            options.append(name)
        for r in rule_matches:
            kw = r.get("keywords", [])
            options.append(kw[0] if kw else "правило")
        sessions.set_state(user_id, "awaiting_clarify")
        options_text = "\n".join(f"• {o}" for o in options)
        await message.answer(
            "Я нашёл несколько вариантов, уточните, пожалуйста:\n\n" + options_text + "\n\n"
            "Напишите точное название или ключевое слово из списка.",
            reply_markup=main_keyboard()
        )
        return

    # ровно 1 совпадение → формируем SOURCE
    if nav_matches:
        label, hint = nav_matches[0]
        source_text = hint
    else:
        rule = rule_matches[0]
        label = "Правило"
        source_text = rule.get("answer", "")

    # вызываем модель чтобы переформулировать source → человеческий ответ
    try:
        answer = await ask_model(user_id=user_id, system_prompt=SYSTEM_PROMPT, source=source_text, user_question=text)
    except Exception as exc:
        answer = f"Ошибка при генерации ответа: {exc}"

    # Если модель вернула сообщение с просьбой уточнить — переводим в состояние уточнения
    low = (answer or "").lower()
    if low.startswith("нужно уточнить") or "уточн" in low and len(low) < 120:
        sessions.set_state(user_id, "awaiting_clarify")
        await message.answer(
            "Мне нужно немного больше деталей, чтобы ответить. Можете уточнить: где именно вы нажали / что видите?",
            reply_markup=main_keyboard()
        )
        return

    # Отправляем ответ и спрашиваем про дополнительные вопросы (модель сама должна добавлять вопрос, но дублируем)
    sessions.append_history(user_id, "assistant", answer)
    await message.answer(answer, reply_markup=main_keyboard())

    sessions.set_state(user_id, "awaiting_more")
    # если модель уже спросила "Есть ли ещё вопросы?" — не дублируем, но safe to ask:
    await message.answer("Есть ли дополнительные вопросы?", reply_markup=main_keyboard())
