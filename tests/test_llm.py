import json
import pytest
from owaw.llm import LLM


class FakeClient:
    """Stub matching the openai client surface we use."""
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

        class _Completions:
            def __init__(self, outer):
                self._outer = outer

            def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                content = self._outer._replies.pop(0)
                return type("R", (), {"choices": [
                    type("C", (), {"message": type("M", (), {"content": content})()})()
                ]})()

        class _Chat:
            def __init__(self, outer):
                self.completions = _Completions(outer)

        self.chat = _Chat(self)


def test_chat_json_parses_object():
    fake = FakeClient(['{"reasoning":"r","entities":[]}'])
    llm = LLM(client=fake, model="m")
    assert llm.chat_json("prompt") == {"reasoning": "r", "entities": []}


def test_chat_json_strips_code_fence():
    fake = FakeClient(['```json\n{"ok":true}\n```'])
    llm = LLM(client=fake, model="m")
    assert llm.chat_json("prompt") == {"ok": True}


def test_chat_json_retries_once_on_garbage():
    fake = FakeClient(["not json at all", '{"ok":true}'])
    llm = LLM(client=fake, model="m")
    assert llm.chat_json("prompt") == {"ok": True}
    assert len(fake.calls) == 2


def test_chat_json_raises_after_retry():
    fake = FakeClient(["garbage", "still garbage"])
    llm = LLM(client=fake, model="m")
    with pytest.raises(ValueError, match="invalid JSON"):
        llm.chat_json("prompt")
