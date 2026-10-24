from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock
import pytest
from aiogram.types import Message
from aiogram_dependency.dependency import Depends


def get_sync_dep():
    return "injected_service"


def get_sync_generator():
    try:
        yield "injected_service"
    finally:
        pass


async def get_async_dep():
    return "injected_service"


async def get_async_generator():
    try:
        yield "injected_service"
    finally:
        pass


@contextmanager
def _sync_contextmanager():
    yield "injected_service"


@asynccontextmanager
async def _async_contextmanager():
    yield "injected_service"


def get_sync_contextmanager():
    with _sync_contextmanager() as cm:
        yield cm


async def get_async_contextmanager():
    async with _async_contextmanager() as cm:
        yield cm


@pytest.mark.parametrize(
    "dependency",
    (
        get_sync_dep,
        get_sync_generator,
        get_async_dep,
        get_async_generator,
        get_sync_contextmanager,
        get_async_contextmanager,
    ),
)
@pytest.mark.asyncio
async def test_dependency_types(dependency, middleware, mock_message, mock_data):
    async def test_handler(event: Message, service: str = Depends(dependency)):
        return service

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    # aiogram calls the next handler as handler(event, data)
    handler = AsyncMock(side_effect=lambda event, data: data["service"])
    result = await middleware(handler, mock_message, mock_data)
    assert result == "injected_service"


@pytest.mark.asyncio
async def test_middleware_handles_handler_exception(middleware, mock_message, mock_data):
    def get_test_service():
        return "service"

    async def failing_handler(event: Message, service: str = Depends(get_test_service)):
        raise ValueError("Handler failed")

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", failing_handler)

    with pytest.raises(ValueError, match="Handler failed"):
        await middleware(failing_handler, mock_message, mock_data)

    # Dependency should still be injected
    # assert mock_data["service"] == "service"


@pytest.mark.asyncio
async def test_middleware_skips_non_dependency_params(middleware, mock_message, mock_data):
    async def test_handler(event: Message, normal_param: str = "default_value", data: dict = None):
        return "result"

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    original_data = mock_data.copy()
    result = await middleware(test_handler, mock_message, mock_data)

    # No dependencies should be added
    assert mock_data == original_data
    assert result == "result"


@pytest.mark.parametrize("is_async", (False, True))
@pytest.mark.asyncio
async def test_generator_sees_handler_exception(is_async, middleware, mock_message, mock_data):
    events = []

    def get_sync_resource():
        try:
            yield "resource"
        except ValueError:
            events.append("rolled back")
            raise
        finally:
            events.append("closed")

    async def get_async_resource():
        try:
            yield "resource"
        except ValueError:
            events.append("rolled back")
            raise
        finally:
            events.append("closed")

    dependency = get_async_resource if is_async else get_sync_resource

    async def test_handler(event: Message, resource: str = Depends(dependency)):
        return resource

    setattr(mock_data["handler"], "callback", test_handler)

    async def failing_handler(event, data):
        events.append(f"handler using {data['resource']}")
        raise ValueError("Handler failed")

    with pytest.raises(ValueError, match="Handler failed"):
        await middleware(failing_handler, mock_message, mock_data)
    assert events == ["handler using resource", "rolled back", "closed"]
