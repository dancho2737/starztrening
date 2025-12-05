# handlers/messages.py
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import re

from ai_responder.responder import ask_ai, sessions

router = Router()

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🆘 Помощь")]],
        resize_keyboard=True
    )

YES_PATTERNS = re.compile(r"^(да|yes|ага|д|конечно|давайте|хочу)\b", flags=re.I)
NO_PATTERNS = re.compile(r"^(нет|не надо|не нужно|не)\b", flags=re.I)

@router.message(lambda message: (message.text or "").strip() == "🆘 Помощь")
async def on_help_button(message: Message):
    user_id = message.from_user.id
    sessions.set_state(user_id, "awaiting_question")
    sessions.append_history(user_id, "user", "clicked_help")
    await message.answer(
        "Привет! Чем могу помочь? Опиши, что ищешь (например: профиль, вывод средств, верификация).",
        reply_markup=main_keyboard()
    )

@router.message()
async def handle_any(message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if not text:
        return await message.answer("Пожалуйста, отправьте текстовое сообщение.", reply_markup=main_keyboard())

    s = sessions.get(user_id)
    sessions.append_history(user_id, "user", text)

    # handle yes/no when awaiting_more
    if s.get("state") == "awaiting_more":
        if NO_PATTERNS.match(text.lower()):
            sessions.set_state(user_id, "idle")
            await message.answer("Хорошо, если понадоблюсь — обращайся. 👋", reply_markup=main_keyboard())
            sessions.append_history(user_id, "assistant", "goodbye")
            return
        if YES_PATTERNS.match(text.lower()):
            sessions.set_state(user_id, "awaiting_question")
            await message.answer("Отлично! Что вас интересует дальше?", reply_markup=main_keyboard())
            return
        await message.answer("Не понял — вы хотите задать ещё вопрос? (Да/Нет)", reply_markup=main_keyboard())
        return

    # Otherwise pass question to ask_ai
    # If user didn't press help, still handle normally
    answer = await ask_ai(user_id, text)
    # ask_ai sets states and logs appropriately
    # If ask_ai returned a message asking to clarify (state awaiting_clarify), it will be the returned text
    await message.answer(answer, reply_markup=main_keyboard())

    # If answer was generated from LLM and state is awaiting_more, ask for follow-up
    if sessions.get(user_id).get("state") == "awaiting_more":
        await message.answer("Есть ли дополнительные вопросы?", reply_markup=main_keyboard())
