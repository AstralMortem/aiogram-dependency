import inspect
from typing import Annotated, Callable, Dict, Any, get_args, get_origin
from .dependency import Dependency, Scope
from .registry import DependencyRegistry
from aiogram.types import TelegramObject


class DependencyResolver:
    def __init__(self, registry: DependencyRegistry):
        self.registry = registry
        self._resolving: set = set()

        self.active_contexts = {}  # Track active context managers
        self.cleanup_tasks = []  # Track cleanup tasks

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
            elif inspect.isasyncgenfunction(dep):
                resolved_value = await self._handle_async_generator(
                    dep, cache_key, **dep_kwargs
                )
            elif inspect.isgeneratorfunction(dep):
                resolved_value = self._handle_generator(dep, cache_key, **dep_kwargs)
            else:
                resolved_value = dep(**dep_kwargs)

                if self._is_sync_contextmanager(resolved_value):
                    resolved_value = self._handle_sync_context_manager(
                        resolved_value, cache_key
                    )
                elif self._is_async_contextmanager(resolved_value):
                    resolved_value = await self._handle_async_context_manager(
                        resolved_value, cache_key
                    )

            # update registry cache
            self.registry.set_dependency(dep, resolved_value, scope, cache_key)
            return resolved_value

        finally:
            # Remove resolving lock
            await self._cleanup_active_context()
            self._resolving.discard(dep)

    def _handle_sync_context_manager(self, context_manager: Any, key: str) -> Any:
        resolved_value = context_manager.__enter__()
        self.active_contexts[key] = context_manager
        return resolved_value

    async def _handle_async_context_manager(
        self, context_manager: Any, key: str
    ) -> Any:
        resolved_value = await context_manager.__aenter__()
        self.active_contexts[key] = context_manager
        return resolved_value

    async def _handle_async_generator(self, dep: Callable, key, **kwargs):
        async_gen = dep(**kwargs)
        try:
            value = await async_gen.__anext__()
            self.active_contexts[key] = async_gen
            return value
        except StopAsyncIteration:
            # Log Error
            return None

    def _handle_generator(self, dep: Callable, key, **kwargs):
        gen = dep(**kwargs)
        try:
            value = next(gen)
            self.active_contexts[key] = gen
            return value
        except StopIteration:
            # Log error
            return None

    async def _cleanup_active_context(self):
        errors = []
        for dep_name, context in list(self.active_contexts.items()):
            try:
                if inspect.isasyncgen(context):
                    try:
                        await context.__anext__()
                    except StopAsyncIteration:
                        pass

                elif inspect.isgenerator(context):
                    try:
                        next(context)
                    except StopIteration:
                        pass
                elif hasattr(context, "__aexit__"):
                    await context.__aexit__(None, None, None)

                elif hasattr(context, "__exit__"):
                    context.__exit__(None, None, None)

                del self.active_contexts[dep_name]
            except Exception as e:
                errors.append(f"Error cleaning up {dep_name}: {e}")

        if errors:
            print(f"Cleanup completed with {len(errors)} errors")

    def _is_sync_contextmanager(self, value) -> bool:
        return hasattr(value, "__enter__") and hasattr(value, "__exit__")

    def _is_async_contextmanager(self, value) -> bool:
        return hasattr(value, "__aenter__") and hasattr(value, "__aexit__")

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
