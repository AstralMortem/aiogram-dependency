import pytest
from aiogram.types import Message
from contextlib import AsyncExitStack
from fastapi import Depends


@pytest.mark.asyncio
async def test_resolve_simple_fastapi_dependency(resolver, mock_message, mock_data):
    def get_service_dep():
        return "test_service"

    async def test_handler(event: Message, service: str = Depends(get_service_dep)):
        return service

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
    assert resolved["service"] == "test_service"


@pytest.mark.asyncio
async def test_resolve_nested_fastapi_dependencies(resolver, mock_message, mock_data):
    # Create nested dependencies
    def get_database():
        return "database_connection"

    def get_user_service(db: str = Depends(get_database)):
        return f"user_service_with_{db}"

    async def test_handler(event: Message, user_service: str = Depends(get_user_service)):
        return user_service

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)

    assert resolved["user_service"] == "user_service_with_database_connection"


@pytest.mark.asyncio
async def test_fastapi_dependency_caching_singleton(resolver, mock_message, mock_data):
    call_count = 0

    def get_singleton_service():
        nonlocal call_count
        call_count += 1
        return f"singleton_{call_count}"

    async def test_handler(
        event: Message,
        service: str = Depends(get_singleton_service, use_cache=True),
    ):
        return service

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        # Resolve twice
        resolved1 = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
        resolved2 = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)

    # Should be called only once due to singleton caching
    assert call_count == 1
    assert resolved1["service"] == resolved2["service"] == "singleton_1"


@pytest.mark.asyncio
async def test_fastapi_dependency_caching_request(resolver, mock_message, mock_data):
    call_count = 0

    def get_request_service():
        nonlocal call_count
        call_count += 1
        return f"request_{call_count}"

    async def test_handler(
        event: Message, service: str = Depends(get_request_service, scope="request")
    ):
        return service

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        # Resolve twice with same message (same cache key)
        resolved1 = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
        resolved2 = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)

    # Should be called only once due to request caching
    assert call_count == 1
    assert resolved1["service"] == resolved2["service"] == "request_1"


@pytest.mark.asyncio
async def test_fastapi_dependency_no_caching_transient(resolver, mock_message, mock_data):
    call_count = 0

    def get_transient_service():
        nonlocal call_count
        call_count += 1
        return f"transient_{call_count}"

    async def test_handler(
        event: Message,
        service: str = Depends(get_transient_service, scope="function"),
    ):
        return service

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        # Resolve twice
        resolved1 = await resolver.resolve_dependencies(mock_message, mock_data.copy(), exit_stack)
        resolved2 = await resolver.resolve_dependencies(mock_message, mock_data.copy(), exit_stack)

    # Should be called twice (no caching)
    assert call_count == 2
    assert resolved1["service"] == "transient_1"
    assert resolved2["service"] == "transient_2"
