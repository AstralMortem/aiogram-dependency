from typing import Dict, Callable, Any
from aiogram.types import TelegramObject
from .dependency import Scope


class DependencyRegistry:
    def __init__(self):
        self._singleton_cache: Dict[Callable, Any] = {}
        self._request_cache: Dict[str, Dict[Callable, Any]] = {}

    def get_cache_key(self, event: TelegramObject, data: Dict[str, Any]) -> str:
        if hasattr(event, "from_user") and event.from_user:
            return f"user_{event.from_user.id}"
        elif hasattr(event, "chat") and event.chat:
            return f"chat_{event.chat.id}"
        else:
            return "global"

    def get_dependency(self, dep: Callable, scope: Scope, cache_key: str):
        if scope == Scope.SINGLETON:
            return self._singleton_cache.get(dep)
        elif scope == Scope.REQUEST:
            return self._request_cache.get(cache_key, {}).get(dep)
        else:
            return None

    def set_dependency(self, dep: Callable, value: Any, scope: Scope, cache_key: str):
        if scope == Scope.SINGLETON:
            self._singleton_cache[dep] = value
        elif scope == Scope.REQUEST:
            if cache_key not in self._request_cache:
                self._request_cache[cache_key] = {}
            self._request_cache[cache_key][dep] = value
