# Aiogram Dependency Injection

A FastAPI-style dependency injection system for aiogram Telegram bots. This library brings clean, type-safe dependency injection to your aiogram handlers, making your code more modular, testable, and maintainable.

[![PyPI Downloads](https://static.pepy.tech/badge/aiogram-dependency)](https://pepy.tech/projects/aiogram-dependency)

## Features

- **FastAPI-style syntax** - Familiar `Depends()` marker, as a default value or inside `Annotated`
- **Three scopes** - Singleton, Request (per update) and Transient
- **Nested dependencies** - Dependencies can depend on other dependencies
- **Any callable** - Sync and async functions, generators with cleanup, classes and callable objects
- **Non-blocking** - Sync dependencies run in a worker thread, off the event loop
- **Automatic cleanup** - `yield` dependencies are closed after the handler, and see its exceptions
- **Event access** - Dependencies receive the event, handler data and other dependencies
- **Circular dependency detection** - Raises a clear error instead of looping
- **Concurrency-safe** - Overlapping updates never share request-scoped dependencies
- **FastAPI support** - Reuse your existing FastAPI `Depends` dependencies

## Installation

```bash
pip install aiogram-dependency
```

With FastAPI `Depends` support:

```bash
pip install "aiogram-dependency[fastapi]"
```

Or install from source:

```bash
git clone https://github.com/AstralMortem/aiogram-dependency
cd aiogram-dependency
pip install -e .
```

Requires Python 3.11+ and aiogram 3.24+.

## Quick Start

```python
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

from aiogram_dependency import Depends, Scope, setup_dependency


class DatabaseConnection:
    def __init__(self, dsn: str):
        self.dsn = dsn

    async def query(self, sql: str) -> str:
        return f"Result for: {sql}"


class UserService:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    async def get_profile(self, user_id: int) -> str:
        return await self.db.query(f"SELECT * FROM users WHERE id = {user_id}")


# Dependency factories
async def get_database() -> DatabaseConnection:
    return DatabaseConnection("postgresql://localhost/mydb")


async def get_user_service(
    db: DatabaseConnection = Depends(get_database, scope=Scope.SINGLETON),
) -> UserService:
    return UserService(db)


# Handler with dependency injection
async def profile_handler(
    message: Message,
    user_service: UserService = Depends(get_user_service),
):
    profile = await user_service.get_profile(message.from_user.id)
    await message.answer(f"Your profile: {profile}")


async def main():
    bot = Bot(token="YOUR_BOT_TOKEN")
    dp = Dispatcher()

    dp.message.register(profile_handler, F.text == "/profile")
    setup_dependency(dp)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

`setup_dependency` can be called before or after registering handlers and including routers. Every router gets dependency injection.

## Dependency Scopes

| Scope | Created | Shared between | Generator closed |
|---|---|---|---|
| `Scope.SINGLETON` | Once, on first use | All updates and users | On dispatcher shutdown |
| `Scope.REQUEST` (default) | Once per update | All parameters and nested dependencies in that update | After the handler finishes |
| `Scope.TRANSIENT` | Every time it is requested | Nothing | After the handler finishes |

### Singleton

Created once and shared by all updates. Use it for expensive, thread-safe objects: database engines, HTTP clients, configuration.

```python
async def get_http_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as client:
        yield client  # closed when the bot shuts down


async def handler(
    message: Message,
    client: httpx.AsyncClient = Depends(get_http_client, scope=Scope.SINGLETON),
):
    ...
```

### Request (default)

Created once per update. If several parameters or nested dependencies ask for the same dependency, they all get the same instance. The next update gets a new one. This is the right scope for database sessions and units of work.

```python
async def get_user_service() -> UserService:
    return UserService()


async def handler(
    message: Message,
    service: UserService = Depends(get_user_service),  # Scope.REQUEST by default
):
    ...
```

### Transient

Created fresh every time it is requested, even twice within one update.

```python
def get_timestamp() -> float:
    return time.time()


async def handler(
    message: Message,
    timestamp: float = Depends(get_timestamp, scope=Scope.TRANSIENT),
):
    ...
```

## Dependency Types

Anything callable can be a dependency:

```python
# Async function
async def get_settings() -> Settings:
    return Settings()


# Sync function: runs in a worker thread, so blocking I/O won't freeze the bot
def load_config() -> dict:
    with open("config.json") as f:
        return json.load(f)


# Class: its __init__ parameters are resolved like any other dependency
class UserRepository:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session


# Callable object: handy for parametrised dependencies
class RequireRole:
    def __init__(self, role: str):
        self.role = role

    async def __call__(self, event: Message, data: dict) -> bool:
        return event.from_user.id in data["roles"].get(self.role, [])


async def handler(
    message: Message,
    repo: UserRepository = Depends(UserRepository),
    is_admin: bool = Depends(RequireRole("admin")),
):
    ...
```

## Generator Dependencies (setup and cleanup)

A dependency that uses `yield` (sync or async) runs its setup before the handler and its cleanup after it. If the handler raises, the exception is thrown into the generator at `yield`, so you can roll back. The `finally` block always runs.

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine("sqlite+aiosqlite:///bot.db")
session_factory = async_sessionmaker(engine)


async def get_session():
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def register_handler(
    message: Message,
    session: AsyncSession = Depends(get_session),
):
    session.add(User(id=message.from_user.id))
    # committed after the handler returns, rolled back if it raises
```

Re-raise the exception in the generator, as above. If a sync generator swallows it, the handler's error is silently lost.

If a dependency fails while dependencies are still being resolved, the generators that were already opened are still closed.

## Annotated

Put the dependency inside `Annotated` to define it once and reuse it everywhere:

```python
from typing import Annotated

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from aiogram_dependency import Depends

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_user(message: Message, session: SessionDep) -> User | None:
    return await session.get(User, message.from_user.id)


UserDep = Annotated[User | None, Depends(get_user)]

router = Router()


@router.message(CommandStart())
async def start(message: Message, user: UserDep):
    await message.answer(f"Hello, {user.name}!" if user else "Hello, stranger!")
```

Other `Annotated` metadata is allowed alongside the dependency, for example `Annotated[str, "docs", Depends(get_name)]`.

## Nested Dependencies

Dependencies can depend on other dependencies, to any depth. A request-scoped dependency used in several places is still created once per update:

```python
async def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


async def get_order_repository(session: SessionDep) -> OrderRepository:
    return OrderRepository(session)


async def get_checkout_service(
    users: UserRepository = Depends(get_user_repository),
    orders: OrderRepository = Depends(get_order_repository),
) -> CheckoutService:
    # both repositories share the same session
    return CheckoutService(users, orders)
```

Circular dependencies (A needs B, B needs A) raise `ValueError: Circular dependency detected`.

## What Dependencies Can Receive

A parameter marked with `Depends(...)` (as its default or inside `Annotated`) is always resolved as a nested dependency. Any other parameter takes the first match from this list:

1. **The event**: a parameter named `event`, `message` or `callback`, or annotated with the event's type (`query: CallbackQuery`, `poll: Poll`, ...).
2. **All handler data**: a parameter named `data` gets the full aiogram data dict.
3. **A handler data key**: a parameter with the same name as a key in the data, such as `bot`, `state`, `event_from_user`, `event_chat`, or anything set by your own middlewares or passed to `Dispatcher(...)`.
4. **Another handler parameter**: a dependency resolved earlier for the same handler, matched by parameter name.
5. Otherwise, the parameter's own default value.

```python
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, User

dp = Dispatcher(admin_ids=[123456])  # becomes data["admin_ids"]


async def is_admin(event_from_user: User, admin_ids: list[int]) -> bool:
    return event_from_user.id in admin_ids


async def get_cart(query: CallbackQuery, state: FSMContext) -> list[str]:
    return (await state.get_data()).get("cart", [])


@router.callback_query(F.data == "checkout")
async def checkout(
    callback_query: CallbackQuery,
    admin: bool = Depends(is_admin),
    cart: list[str] = Depends(get_cart),
):
    ...
```

## FastAPI Integration

If your bot shares code with a FastAPI app, you can use FastAPI's `Depends` directly. Install the extra with `pip install "aiogram-dependency[fastapi]"`.

```python
from typing import Annotated

from fastapi import Depends

SessionDep = Annotated[AsyncSession, Depends(get_session)]  # same alias as your API


@router.message(Command("orders"))
async def orders(message: Message, session: SessionDep):
    ...
```

FastAPI options map to scopes like this:

| FastAPI | Scope |
|---|---|
| `Depends(dep)` (`use_cache=True`, the default) | `Scope.REQUEST` |
| `Depends(dep, use_cache=False)` | `Scope.TRANSIENT` |
| `Depends(dep, scope="function")` | `Scope.TRANSIENT` |
| `Depends(dep, scope="request")` | `Scope.REQUEST` |

FastAPI-only parameters such as `Request`, `Header()` or `Query()` are not available in a bot. Dependencies that need them can't be shared.

## Configuring `setup_dependency`

```python
from aiogram_dependency import setup_dependency
from aiogram_dependency.registry import DependencyRegistry

registry = setup_dependency(
    dp,
    allowed_updates=["message", "callback_query"],  # optional
    registry=DependencyRegistry(),  # optional
)
```

- **`allowed_updates`**: the update types that get dependency injection. By default it covers every update type except the `error` observer. Unknown names raise `ValueError`. To use dependencies in error handlers, list `"error"` along with every other update type you need.
- **`registry`**: the `DependencyRegistry` that holds singletons. A new one is created when omitted. The registry is returned in either case.
- On dispatcher shutdown, `registry.close()` runs automatically. It closes singleton generators and clears the singleton cache.

### Providing singletons yourself

You can put a ready-made instance into the registry, keyed by the dependency function:

```python
registry = DependencyRegistry()
registry.singleton_cache[get_database] = DatabaseConnection("custom://connection")

setup_dependency(dp, registry=registry)

# Handlers using Depends(get_database, scope=Scope.SINGLETON) now receive this instance
```

## Testing

Handlers are plain functions, so in unit tests you can call them with test doubles and skip dependency injection entirely:

```python
from unittest.mock import AsyncMock


async def test_profile_handler():
    message = AsyncMock()
    message.from_user.id = 1
    service = AsyncMock()
    service.get_profile.return_value = "profile"

    await profile_handler(message, user_service=service)

    message.answer.assert_awaited_once_with("Your profile: profile")
```

To test the whole flow, including dependencies, feed an update through a real dispatcher. No network access is needed until a handler calls the Bot API:

```python
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, Update, User


async def test_callback_flow():
    dp = Dispatcher()
    dp.include_router(router)
    setup_dependency(dp)

    update = Update(
        update_id=1,
        callback_query=CallbackQuery(
            id="1",
            from_user=User(id=1, is_bot=False, first_name="John"),
            chat_instance="chat",
            data="checkout",
        ),
    )
    bot = Bot("42:TEST")
    try:
        result = await dp.feed_update(bot, update)  # the handler's return value
    finally:
        await bot.session.close()
```

Run the library's own test suite:

```bash
uv sync --all-groups
uv run pytest
```

## Limitations

- Event type matching needs real annotations. With `from __future__ import annotations` they become strings, so name the parameter `event`, `message` or `callback` instead.
- Dependencies are used as cache keys, so they must be hashable. Plain functions and classes always are.
- If two updates are the first to use a singleton at the same moment, it can be created twice. Create critical singletons up front with `registry.singleton_cache`.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Related Projects

- [aiogram](https://github.com/aiogram/aiogram) - Modern and fully asynchronous framework for Telegram Bot API
- [FastAPI](https://github.com/tiangolo/fastapi) - Modern, fast web framework for building APIs with Python
