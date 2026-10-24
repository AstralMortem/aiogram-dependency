import asyncio
import threading
from typing import Annotated
import pytest
from aiogram.types import Message
from aiogram_dependency.dependency import Depends, Scope
from aiogram_dependency.utils import run_in_threadpool
from contextlib import AsyncExitStack


@pytest.mark.asyncio
async def test_resolve_simple_dependency(resolver, mock_message, mock_data):
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
async def test_resolve_nested_dependencies(resolver, mock_message, mock_data):
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
async def test_circular_dependency_detection(resolver, mock_message, mock_data):
    def dep_a(b=None):
        return f"a_with_{b}"

    def dep_b(a=Depends(dep_a)):
        return f"b_with_{a}"

    # dep_b doesn't exist when dep_a is defined, so close the cycle afterwards
    dep_a.__defaults__ = (Depends(dep_b),)

    async def test_handler(event: Message, service_a: str = Depends(dep_a)):
        return service_a

    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        with pytest.raises(ValueError, match="Circular dependency detected"):
            await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_state(resolver, mock_message, mock_data):
    closed = []
    count = 0

    async def get_session():
        nonlocal count
        count += 1
        session = f"session_{count}"
        await asyncio.sleep(0.01)
        yield session
        closed.append(session)

    async def test_handler(event: Message, session: str = Depends(get_session)):
        return session

    setattr(mock_data["handler"], "callback", test_handler)

    async def request():
        async with AsyncExitStack() as exit_stack:
            resolved = await resolver.resolve_dependencies(
                mock_message, mock_data.copy(), exit_stack
            )
            # Session must still be open while its own handler runs
            assert resolved["session"] not in closed
            return resolved["session"]

    # Same user, overlapping updates: no false circular error, one session each
    sessions = await asyncio.gather(request(), request())
    assert sorted(sessions) == ["session_1", "session_2"]


@pytest.mark.asyncio
async def test_dependency_caching_singleton(resolver, mock_message, mock_data):
    call_count = 0

    def get_singleton_service():
        nonlocal call_count
        call_count += 1
        return f"singleton_{call_count}"

    async def test_handler(
        event: Message,
        service: str = Depends(get_singleton_service, scope=Scope.SINGLETON),
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
async def test_dependency_caching_request(resolver, mock_message, mock_data):
    call_count = 0

    def get_request_service():
        nonlocal call_count
        call_count += 1
        return f"request_{call_count}"

    def get_consumer(service: str = Depends(get_request_service, scope=Scope.REQUEST)):
        return service

    async def test_handler(
        event: Message,
        service: str = Depends(get_request_service, scope=Scope.REQUEST),
        consumer: str = Depends(get_consumer),
    ):
        return service

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved1 = await resolver.resolve_dependencies(mock_message, mock_data.copy(), exit_stack)
        resolved2 = await resolver.resolve_dependencies(mock_message, mock_data.copy(), exit_stack)

    # Shared within one request, fresh for the next one
    assert resolved1["service"] == resolved1["consumer"] == "request_1"
    assert resolved2["service"] == resolved2["consumer"] == "request_2"
    assert call_count == 2


@pytest.mark.asyncio
async def test_dependency_no_caching_transient(resolver, mock_message, mock_data):
    call_count = 0

    def get_transient_service():
        nonlocal call_count
        call_count += 1
        return f"transient_{call_count}"

    async def test_handler(
        event: Message,
        service: str = Depends(get_transient_service, scope=Scope.TRANSIENT),
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


@pytest.mark.asyncio
async def test_annotated_with_extra_metadata(resolver, mock_message, mock_data):
    def get_service():
        return "service"

    async def test_handler(event: Message, service: Annotated[str, "docs", Depends(get_service)]):
        return service

    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
    assert resolved["service"] == "service"


@pytest.mark.asyncio
async def test_run_in_threadpool_positional_args():
    assert await run_in_threadpool(lambda a, b=0: a + b, 1, b=2) == 3


@pytest.mark.asyncio
async def test_empty_depends_resolves_to_none(resolver, mock_message, mock_data):
    async def test_handler(event: Message, service: str = Depends()):
        return service

    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
    assert resolved["service"] is None


@pytest.mark.asyncio
async def test_dependency_receives_event_data_and_sibling_params(resolver, mock_message, mock_data):
    def get_settings():
        return "settings"

    def get_service(message, data: dict, bot, settings):
        # event by name, whole data dict, a data key, and an earlier handler param
        return message, data, bot, settings

    async def test_handler(
        event: Message,
        settings: str = Depends(get_settings),
        service: tuple = Depends(get_service),
    ):
        return service

    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)

    message, data, bot, settings = resolved["service"]
    assert message is mock_message
    assert data is mock_data
    assert bot is mock_data["bot"]
    assert settings == "settings"


@pytest.mark.asyncio
async def test_class_and_callable_instance_dependencies(resolver, mock_message, mock_data):
    class UserService:
        def __init__(self, event: Message):
            self.event = event

    class AsyncFactory:
        async def __call__(self):
            return "from_async_call"

    factory = AsyncFactory()

    async def test_handler(
        event: Message,
        service: UserService = Depends(UserService),
        value: str = Depends(factory),
    ):
        return service

    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)

    assert isinstance(resolved["service"], UserService)
    assert resolved["service"].event is mock_message
    assert resolved["value"] == "from_async_call"


@pytest.mark.asyncio
async def test_sync_dependency_runs_in_thread(resolver, mock_message, mock_data):
    def get_thread():
        return threading.current_thread()

    async def test_handler(event: Message, thread=Depends(get_thread)):
        return thread

    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
    assert resolved["thread"] is not threading.main_thread()


@pytest.mark.asyncio
async def test_failing_dependency_closes_already_opened_ones(resolver, mock_message, mock_data):
    events = []

    async def get_session():
        try:
            yield "session"
        finally:
            events.append("session closed")

    def get_broken():
        raise RuntimeError("broken")

    async def test_handler(
        event: Message,
        session: str = Depends(get_session),
        broken: str = Depends(get_broken),
    ):
        return session

    setattr(mock_data["handler"], "callback", test_handler)

    with pytest.raises(RuntimeError, match="broken"):
        async with AsyncExitStack() as exit_stack:
            await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
    assert events == ["session closed"]


@pytest.mark.asyncio
async def test_annotated_without_dependency_is_ignored(resolver, mock_message, mock_data):
    async def test_handler(event: Message, text: Annotated[str, "docs"] = "default"):
        return text

    setattr(mock_data["handler"], "callback", test_handler)

    async with AsyncExitStack() as exit_stack:
        resolved = await resolver.resolve_dependencies(mock_message, mock_data, exit_stack)
    assert "text" not in resolved


@pytest.mark.asyncio
async def test_missing_handler_raises(resolver, mock_message):
    async with AsyncExitStack() as exit_stack:
        with pytest.raises(ValueError, match="Callable not found"):
            await resolver.resolve_dependencies(mock_message, {}, exit_stack)
