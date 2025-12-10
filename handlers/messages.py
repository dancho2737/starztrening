from aiogram import Router
from aiogram.types import Message
from ai_responder.responder import ask_ai, sessions, user_device

router = Router()

@router.message()
async def handle_message(msg: Message):
    user = msg.from_user.id
    text = (msg.text or "").strip().lower()

    # Если это новое сообщение и устройство ещё не выбрано
    if user not in user_device:
        # Если пользователь отвечает "смартфон" или "компьютер"
        if text in ["смартфон", "телефон", "mobile"]:
            user_device[user] = "mobile"
            return await msg.answer("Отлично! Работает мобильная навигация. Чем могу помочь?")
        
        if text in ["компьютер", "пк", "desktop"]:
            user_device[user] = "desktop"
            return await msg.answer("Отлично! Работает навигация для компьютера. Что вас интересует?")
        
        # Если он написал что-то другое → бот спрашивает устройство
        return await msg.answer(
            "Привет! 😊\nПеред началом подскажите, с какого устройства вы пользуетесь:\n\n"
            "📱 *Смартфон*\n💻 *Компьютер*"
        )

    # --- Если устройство уже выбрано — идём по обычному пути ---
    sessions.add(user, "user", text)

    try:
        answer = await ask_ai(user, text)
        await msg.answer(answer)
    except Exception as e:
        await msg.answer(f"⚠️ Ошибка: <code>{e}</code>")
