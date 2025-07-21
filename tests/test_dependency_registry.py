import pytest
from aiogram_dependency.dependency import Scope
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
    cache_key = registry.get_cache_key(messages, {})
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

    registry.set_dependency(dummy_dep, value, scope, cache_key)
    retrived = registry.get_dependency(dummy_dep, scope, cache_key)
    assert retrived == value


def test_request_cache_isolation(registry):
    def dummy_dep():
        return "request_value"

    value1 = "value_for_user_1"
    value2 = "value_for_user_2"

    registry.set_dependency(dummy_dep, value1, Scope.REQUEST, "user_1")
    registry.set_dependency(dummy_dep, value2, Scope.REQUEST, "user_2")

    assert registry.get_dependency(dummy_dep, Scope.REQUEST, "user_1") == value1
    assert registry.get_dependency(dummy_dep, Scope.REQUEST, "user_2") == value2
