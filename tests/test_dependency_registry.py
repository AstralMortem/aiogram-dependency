import pytest
from aiogram_dependency.dependency import Depends, Scope
from aiogram.types import User, Chat, Message
from unittest.mock import Mock


def message_with_user():
    user = Mock(spec=User)
    user.id = 123
    user.first_name = "John"
    message = Mock(spec=Message)
    message.from_user = user
    message.text = "test message"
    return message


def message_with_chat():
    chat = Mock(spec=Chat)
    chat.id = 456
    chat.type = "private"
    message = Mock(spec=Message)
    message.chat = chat
    message.text = "test message"
    return message


def empty_message():
    message = Mock(spec=Message)
    message.text = "test message"
    return message


@pytest.mark.parametrize(
    "messages, key",
    [
        (message_with_user(), "user_123"),
        (message_with_chat(), "chat_456"),
        (empty_message(), "global"),
    ],
)
def test_cache_generation_with_params(messages, key, registry):
    cache_key = registry.get_cache_key(messages)
    assert cache_key == key


@pytest.mark.parametrize(
    "value, cache_key, scope",
    [
        ("test_value", "test_key", Scope.SINGLETON),
        ("test_value", "user_123", Scope.REQUEST),
        (None, "test_key", Scope.TRANSIENT),
    ],
)
def test_cache_storage_and_retrieval(value, cache_key, scope, registry):
    def dummy_dep():
        return str(scope)

    dependency: str = Depends(dummy_dep, scope=scope)

    registry.set_dependency(dependency, value, cache_key)
    retrived = registry.get_dependency(dependency, cache_key)
    assert retrived == value


def test_request_cache_isolation(registry):
    def dummy_dep():
        return "request_value"

    dependency = Depends(dummy_dep, scope=Scope.REQUEST)

    value1 = "value_for_user_1"
    value2 = "value_for_user_2"

    registry.set_dependency(dependency, value1, "user_1")
    registry.set_dependency(dependency, value2, "user_2")

    assert registry.get_dependency(dependency, "user_1") == value1
    assert registry.get_dependency(dependency, "user_2") == value2
