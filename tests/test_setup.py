import pytest
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher, Router
from aiogram.types import CallbackQuery, Update, User
from aiogram_dependency import Depends, setup_dependency
from aiogram_dependency.middleware import DependencyMiddleware
from aiogram_dependency.registry import DependencyRegistry


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


def test_setup_rejects_non_dispatcher():
    with pytest.raises(TypeError):
        setup_dependency(Router())


def test_setup_rejects_unknown_update_type():
    with pytest.raises(ValueError, match="not_an_update"):
        setup_dependency(Dispatcher(), allowed_updates=["not_an_update"])


def test_setup_allowed_updates_limits_observers():
    dp = Dispatcher()
    setup_dependency(dp, allowed_updates=["message"])

    def has_dependency_middleware(observer):
        return any(isinstance(m, DependencyMiddleware) for m in observer.middleware)

    assert has_dependency_middleware(dp.message)
    assert not has_dependency_middleware(dp.callback_query)
    assert not has_dependency_middleware(dp.update)


@pytest.mark.asyncio
async def test_shutdown_closes_singletons():
    registry = DependencyRegistry()
    dp = Dispatcher()
    assert setup_dependency(dp, registry=registry) is registry

    closed = []

    async def resource():
        yield
        closed.append(True)

    await registry.exit_stack.enter_async_context(asynccontextmanager(resource)())
    await dp.emit_shutdown()
    assert closed == [True]
