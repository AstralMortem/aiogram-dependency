import inspect
from typing import Annotated, Callable, Dict, Any, get_args, get_origin
from .dependency import Dependency, Scope
from .registry import DependencyRegistry
from aiogram.types import TelegramObject


class DependencyResolver:
    def __init__(self, registry: DependencyRegistry):
        self.registry = registry
        self._resolving: set = set()

    async def resolve_dependencies(self, event: TelegramObject, data: Dict[str, Any]):
        # Callable stored in HandlerObject dataclass, which in `data` dict;
        # Try to get callable
        call = data.get("handler", None)
        if call and hasattr(call, "callback"):
            func = getattr(call, "callback")
            sig = inspect.signature(func)
            cache_key = self.registry.get_cache_key(event, data)
            resolved_deps = {}

            for param_name, param in sig.parameters.items():
                if self._is_dependency_param(param):
                    dep, scope = self._get_dependency_from_param(param)
                    # If dependency inside Dependency class empty just skip
                    if dep is None:
                        resolved_deps[param_name] = None
                        continue

                    # Check if circular dependency
                    if dep in self._resolving:
                        raise ValueError(
                            f"Circular dependency detected: {dep.__name__}"
                        )
                    # Call main resolver
                    resolved_value = await self._resolve_single_dependency(
                        dep, scope, event, data, cache_key, resolved_deps
                    )
                    resolved_deps[param_name] = resolved_value
            return resolved_deps
        return {}

    async def _resolve_single_dependency(
        self,
        dep: Callable,
        scope: Scope,
        event: TelegramObject,
        data: Dict[str, Any],
        cache_key: str,
        resolved_deps: Dict[str, Any],
    ):
        # Check if dependency in cache, return if True
        cached_value = self.registry.get_dependency(dep, scope, cache_key)
        if cached_value is not None:
            return cached_value

        # Add resolving lock
        self._resolving.add(dep)

        try:
            dep_sig = inspect.signature(dep)
            dep_kwargs = {}
            nested_dependencies = set()

            for param_name, param in dep_sig.parameters.items():
                # set default aiogram kwargs, message, event, etc..
                if param_name == "event":
                    dep_kwargs[param_name] = event
                elif param_name == "data":
                    dep_kwargs[param_name] = data
                elif param_name in data:
                    dep_kwargs[param_name] = data[param_name]
                elif param_name in resolved_deps:
                    dep_kwargs[param_name] = resolved_deps[param_name]

                # check if dependency
                elif self._is_dependency_param(param):
                    # Recursivly resolve dependencies
                    nested_dep, nested_scope = self._get_dependency_from_param(param)
                    nested_dependencies.add(nested_dep)
                    nested_value = await self._resolve_single_dependency(
                        nested_dep, nested_scope, event, data, cache_key, resolved_deps
                    )
                    dep_kwargs[param_name] = nested_value

            # After resolving kwargs, call dpendency callable with proper kwargs
            if inspect.iscoroutinefunction(dep):
                resolved_value = await dep(**dep_kwargs)
            else:
                resolved_value = dep(**dep_kwargs)

            # update registry cache
            self.registry.set_dependency(dep, resolved_value, scope, cache_key)
            return resolved_value

        finally:
            # Remove resolving lock
            self._resolving.discard(dep)

    def _get_dependency_from_param(self, param: inspect.Parameter) -> Dependency:
        # Extract Dependency class from Annotated or param.default
        if get_origin(param.annotation) is Annotated:
            for meta in get_args(param.annotation)[1:]:
                if isinstance(meta, Dependency):
                    return (meta.dependency, meta.scope)
        elif isinstance(param.default, Dependency):
            return (param.default.dependency, param.default.scope)

        return False, None

    def _is_dependency_param(self, param: inspect.Parameter) -> bool:
        # Check if param is Annotated[..., Depends()] or direct Depends()
        if get_origin(param.annotation) is Annotated:
            for meta in get_args(param.annotation)[1:]:
                if isinstance(meta, Dependency):
                    return True
        elif isinstance(param.default, Dependency):
            return True
        return False
