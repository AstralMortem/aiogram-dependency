from typing import Dict, Any
from aiogram.types import TelegramObject
from .dependency import Dependency, Scope


class DependencyRegistry:
    def __init__(self):
        self._singleton_cache: Dict[int, Any] = {}
        self._request_cache: Dict[str, Dict[int, Any]] = {}

    def get_cache_key(self, event: TelegramObject) -> str:
        if hasattr(event, "from_user") and event.from_user:
            return f"user_{event.from_user.id}"
        elif hasattr(event, "chat") and event.chat:
            return f"chat_{event.chat.id}"
        else:
            return "global"

    def get_dependency(self, dependency: Dependency, cache_key: str):
        dep_key = hash(dependency.dependency)
        if dependency.scope == Scope.SINGLETON:
            return self._singleton_cache.get(dep_key)
        elif dependency.scope == Scope.REQUEST:
            return self._request_cache.get(cache_key, {}).get(dep_key)
        else:
            return None

    def set_dependency(self, dependency: Dependency, value: Any, cache_key: str):
        dep_key = hash(dependency.dependency)
        if dependency.scope == Scope.SINGLETON:
            self._singleton_cache[dep_key] = value
        elif dependency.scope == Scope.REQUEST:
            if cache_key not in self._request_cache:
                self._request_cache[cache_key] = {}
            self._request_cache[cache_key][dep_key] = value

    def reset_request_cache(self):
        self._request_cache = {}

    def reset_singletone_cache(self):
        self._singleton_cache = {}
