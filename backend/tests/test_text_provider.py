"""Writing the histories on OpenAI, or on any provider that speaks its API."""
import asyncio
import importlib
import sys
import types

import pytest


def _load(monkeypatch, **env):
    """openai_voice with a given environment, and openai/lameenc stood in for."""
    for name, stub in (("openai", types.SimpleNamespace(AsyncOpenAI=None)), ("lameenc", types.SimpleNamespace(Encoder=object))):
        try:
            importlib.import_module(name)
        except ImportError:
            sys.modules[name] = stub
    for key in ("TEXT_API_BASE", "TEXT_API_KEY", "OPENAI_TEXT_MODEL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("openai_voice", None)
    return importlib.import_module("openai_voice")


class FakeClient:
    """Records how it was built and which API was called."""
    calls: list = []

    def __init__(self, **kwargs):
        FakeClient.calls.append(kwargs)
        done = types.SimpleNamespace(content="chat said so")
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
            create=self._record("chat", types.SimpleNamespace(choices=[types.SimpleNamespace(message=done)]))))
        self.responses = types.SimpleNamespace(
            create=self._record("responses", types.SimpleNamespace(output_text="responses said so")))

    @staticmethod
    def _record(which, result):
        async def call(**kwargs):
            FakeClient.calls.append({"api": which, **kwargs})
            return result
        return call


@pytest.fixture(autouse=True)
def _clear():
    FakeClient.calls = []


def test_openai_by_default_uses_the_responses_api(monkeypatch):
    ov = _load(monkeypatch)
    monkeypatch.setattr(ov, "AsyncOpenAI", FakeClient)
    assert ov.text_provider() == "OpenAI"
    assert asyncio.run(ov.generate_text("sk-key", "rules", "a street")) == "responses said so"
    assert FakeClient.calls[0] == {"api_key": "sk-key"}  # no base_url: OpenAI's own endpoint
    assert FakeClient.calls[1]["api"] == "responses"


def test_another_provider_uses_chat_completions_and_its_own_key(monkeypatch):
    ov = _load(monkeypatch, TEXT_API_BASE="https://generativelanguage.googleapis.com/v1beta/openai/",
               TEXT_API_KEY="AIza-google", OPENAI_TEXT_MODEL="some-flash")
    monkeypatch.setattr(ov, "AsyncOpenAI", FakeClient)
    assert ov.text_provider() == "Google"
    assert asyncio.run(ov.generate_text("sk-openai", "rules", "a street")) == "chat said so"
    built, call = FakeClient.calls[0], FakeClient.calls[1]
    assert built["api_key"] == "AIza-google" and built["base_url"].endswith("/v1beta/openai/")
    assert call["api"] == "chat" and call["model"] == "some-flash"
    assert [m["role"] for m in call["messages"]] == ["system", "user"]


def test_a_provider_without_its_own_key_falls_back_to_the_openai_key(monkeypatch):
    ov = _load(monkeypatch, TEXT_API_BASE="https://example.test/v1/")
    monkeypatch.setattr(ov, "AsyncOpenAI", FakeClient)
    asyncio.run(ov.generate_text("sk-openai", "rules", "a street"))
    assert FakeClient.calls[0]["api_key"] == "sk-openai"
    assert ov.text_provider() == "example.test"
