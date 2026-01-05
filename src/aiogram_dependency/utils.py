from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
import functools
import asyncio
import inspect
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    ParamSpec,
    TypeVar,
    ContextManager,
    get_args,
    get_origin,
)

from aiogram_dependency.dependency import Dependency, Scope

try:
    from fastapi.params import Depends as FastAPIDependency
except ImportError:
    FastAPIDependency = None

_T = TypeVar("_T")
_P = ParamSpec("_P")


async def run_in_threadpool(func: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> _T:
    func = functools.partial(func, *args, **kwargs)
    return await asyncio.to_thread(func, *args, **kwargs)


@asynccontextmanager
async def contextmanager_in_threadpool(cm: ContextManager[_T]) -> AsyncGenerator[_T, None]:
    try:
        yield await run_in_threadpool(cm.__enter__)
    except Exception as e:
        ok = bool(await asyncio.to_thread(cm.__exit__, type(e), e, None))
        if not ok:
            raise e
    else:
        await asyncio.to_thread(cm.__exit__, None, None, None)


def is_coroutine_callable(func: Callable[..., Any]) -> bool:
    # From fastapi source:
    if inspect.isroutine(func):
        return inspect.iscoroutinefunction(func)
    if inspect.isclass(func):
        return False
    dunder_call = getattr(func, "__call__", None)
    return inspect.iscoroutinefunction(dunder_call)


def is_async_gen_callable(func: Callable[..., Any]) -> bool:
    if inspect.isasyncgenfunction(func):
        return True
    dunder_call = getattr(func, "__call__", None)
    return inspect.isasyncgenfunction(dunder_call)


def is_gen_callable(func: Callable[..., Any]) -> bool:
    if inspect.isgeneratorfunction(func):
        return True
    dunder_call = getattr(func, "__call__", None)
    return inspect.isgeneratorfunction(dunder_call)


async def solve_generator(
    *, call: Callable[..., Any], stack: AsyncExitStack, kwargs: Dict[str, Any]
) -> Any:
    if is_gen_callable(call):
        cm = contextmanager_in_threadpool(contextmanager(call)(**kwargs))
    elif is_async_gen_callable(call):
        cm = asynccontextmanager(call)(**kwargs)
    return await stack.enter_async_context(cm)


def extract_handler_signature(data: Dict[str, Any]) -> inspect.Signature:
    handler = data.get("handler")
    if hasattr(handler, "callback"):
        return inspect.signature(getattr(handler, "callback"))
    raise ValueError("Callable not found")


def _extract_fastapi_scope(dependency: FastAPIDependency):
    if dependency.scope == "request":
        return Scope.REQUEST
    if dependency.scope == "function":
        return Scope.TRANSIENT
    if dependency.use_cache:
        return Scope.SINGLETON
    return Scope.REQUEST


def _as_fastapi_dependency(obj: Any):
    if FastAPIDependency is not None and isinstance(obj, FastAPIDependency):
        return Dependency(dependency=obj.dependency, scope=_extract_fastapi_scope(obj))
    return False


def extract_dependency(param: inspect.Parameter) -> Dependency | bool:
    if get_origin(param.annotation) is Annotated:
        for meta in get_args(param.annotation)[1:]:
            if isinstance(meta, Dependency):
                return meta
            else:
                return _as_fastapi_dependency(meta)
    elif isinstance(param.default, Dependency):
        return param.default
    else:
        return _as_fastapi_dependency(param.default)
