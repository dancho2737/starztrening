from aiogram import Router, types

router = Router()


@router.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    await callback.answer("Кнопки пока в разработке.")
