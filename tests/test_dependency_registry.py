import pytest
from contextlib import AsyncExitStack
from aiogram.types import Message
from aiogram_dependency.dependency import Depends, Scope


@pytest.mark.asyncio
async def test_singleton_generator_lives_until_registry_close(
    registry, resolver, mock_message, mock_data
):
    state = {}

    async def get_engine():
        state["open"] = True
        yield state
        state["open"] = False

    async def test_handler(
        event: Message, engine: dict = Depends(get_engine, scope=Scope.SINGLETON)
    ):
        return engine

    setattr(mock_data["handler"], "callback", test_handler)

    for _ in range(2):
        async with AsyncExitStack() as exit_stack:
            resolved = await resolver.resolve_dependencies(
                mock_message, mock_data.copy(), exit_stack
            )
        # Still open after the request that created it has finished
        assert resolved["engine"]["open"] is True

    await registry.close()
    assert state["open"] is False
    assert registry.singleton_cache == {}
