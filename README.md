# Aiogram Dependency Injection

A FastAPI-style dependency injection system for aiogram Telegram bots. This library brings clean, type-safe dependency injection to your aiogram handlers, making your code more modular, testable, and maintainable.

[![PyPI Downloads](https://static.pepy.tech/badge/aiogram-dependency)](https://pepy.tech/projects/aiogram-dependency)
## Features

- 🚀 **FastAPI-style syntax** - Familiar `Depends()` decorator
- 🔄 **Multiple dependency scopes** - Singleton, Request, and Transient
- 🏗️ **Nested dependencies** - Dependencies can depend on other dependencies
- ⚡ **Async support** - Both sync and async dependency functions
- 🛡️ **Circular dependency detection** - Prevents infinite loops
- 🧪 **Type-safe** - Full type hints support
- 💾 **Smart caching** - Efficient resource management

## Installation

```bash
pip install aiogram-dependency
```

Or install from source:

```bash
git clone https://github.com/AstralMortem/aiogram-dependency
cd aiogram-dependency
pip install -e .
```

## Quick Start

```python
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

from aiogram_dependency import Depends, DependencyMiddleware, Scope

# Define your dependencies
class DatabaseConnection:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
    
    async def query(self, sql: str):
        # Your database logic here
        return f"Result for: {sql}"

class UserService:
    def __init__(self, db: DatabaseConnection):
        self.db = db
    
    async def get_user_profile(self, user_id: int):
        return await self.db.query(f"SELECT * FROM users WHERE id = {user_id}")

# Dependency factories
async def get_database() -> DatabaseConnection:
    return DatabaseConnection("postgresql://localhost/mydb")

async def get_user_service(
    db: DatabaseConnection = Depends(get_database, scope=Scope.SINGLETON)
) -> UserService:
    return UserService(db)

# Handler with dependency injection
async def profile_handler(
    message: Message,
    user_service: UserService = Depends(get_user_service)
):
    if not message.from_user:
        await message.answer("User not found")
        return
    
    profile = await user_service.get_user_profile(message.from_user.id)
    await message.answer(f"Your profile: {profile}")

# Setup bot
async def main():
    bot = Bot(token="YOUR_BOT_TOKEN")
    dp = Dispatcher()
    
    # Register dependency injection middleware
    dp.message.middleware(DependencyMiddleware())
    
    # Register handlers
    dp.message.register(profile_handler, F.text == "/profile")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## Dependency Scopes

### Singleton
Created once and shared across all requests globally.

```python
async def get_database() -> DatabaseConnection:
    return DatabaseConnection("connection_string")

async def handler(
    message: Message,
    db: DatabaseConnection = Depends(get_database, scope=DependencyScope.SINGLETON)
):
    # Same database instance for all users
    pass
```

### Request (Default)
Created once per user/chat and cached for subsequent calls in the same context.

```python
async def get_user_service() -> UserService:
    return UserService()

async def handler(
    message: Message,
    service: UserService = Depends(get_user_service, scope=DependencyScope.REQUEST)
):
    # Same service instance for this user, different for other users
    pass
```

### Transient
Created fresh every time it's requested.

```python
async def get_timestamp() -> float:
    return time.time()

async def handler(
    message: Message,
    timestamp: float = Depends(get_timestamp, scope=DependencyScope.TRANSIENT)
):
    # New timestamp every time
    pass
```

## Advanced Usage

### Annotated

You can use Annotated type to make it more readable.
```python
from typing import Annotated
from aiogram_dependency import Depends
from aiogram import Dispatcher,filters,types

async def get_database() -> DatabaseConnection:
    return DatabaseConnection("postgresql://localhost/db")

DatabaseDep = Annotated[DatabaseConnection, Depends(get_database)]

async def get_user(db: DatabaseDep):
    return db.execute('SQL')

UserDep = Annotated[dict, Depends(get_user)]

dp = Dispatcher()

@dp.message(filters.CommandStart())
async def start(message:types.Message, user: UserDep):
    return await message.answer(user['username'])


```


### Nested Dependencies

Dependencies can depend on other dependencies:

```python
async def get_database() -> DatabaseConnection:
    return DatabaseConnection("postgresql://localhost/db")

async def get_user_repository(
    db: DatabaseConnection = Depends(get_database)
) -> UserRepository:
    return UserRepository(db)

async def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
    notification_service: NotificationService = Depends(get_notification_service)
) -> UserService:
    return UserService(user_repo, notification_service)
```

### Using Event Data in Dependencies

Dependencies can access the current event and handler data:

```python
async def get_current_user(event: Message) -> Optional[User]:
    return event.from_user

async def get_user_permissions(
    event: Message,
    data: dict,
    current_user: User = Depends(get_current_user)
) -> List[str]:
    # Access event, data, and other dependencies
    if current_user and current_user.id in data.get('admins', []):
        return ['admin', 'user']
    return ['user']

async def admin_handler(
    message: Message,
    permissions: List[str] = Depends(get_user_permissions)
):
    if 'admin' not in permissions:
        await message.answer("Access denied")
        return
    
    await message.answer("Welcome, admin!")
```

### Custom Registry and Resolver

For advanced use cases, you can customize the dependency system:

```python
from aiogram_dependency.registry import DependencyRegistry
from aiogram_dependency.resolver import DependencyResolver
from aiogram_dependency import DependencyMiddleware

# Create custom registry
registry = DependencyRegistry()

# Pre-populate with some dependencies
registry.set_dependency(
    get_database, 
    DatabaseConnection("custom://connection"),
    DependencyScope.SINGLETON,
    "global"
)

# Use custom middleware
middleware = DependencyMiddleware(registry)
dp.message.middleware(middleware)
```

## Testing

The library is fully testable. Here's an example:


Run the full test suite:

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=aiogram_dependency --cov-report=html
```



## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## Related Projects

- [aiogram](https://github.com/aiogram/aiogram) - Modern and fully asynchronous framework for Telegram Bot API
- [FastAPI](https://github.com/tiangolo/fastapi) - Modern, fast web framework for building APIs with Python
