import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import CallbackQuery, Update, User
from aiogram_dependency import Depends, setup_dependency


@pytest.mark.asyncio
async def test_router_included_after_setup_gets_dependencies():
    dp = Dispatcher()
    setup_dependency(dp)

    def get_query_id(query: CallbackQuery):
        return f"service_for_{query.id}"

    router = Router()

    @router.callback_query()
    async def handler(callback_query: CallbackQuery, service: str = Depends(get_query_id)):
        return service

    dp.include_router(router)

    update = Update(
        update_id=1,
        callback_query=CallbackQuery(
            id="42",
            from_user=User(id=1, is_bot=False, first_name="John"),
            chat_instance="chat",
            data="data",
        ),
    )
    bot = Bot("42:TEST")
    try:
        assert await dp.feed_update(bot, update) == "service_for_42"
    finally:
        await bot.session.close()
