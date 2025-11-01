import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.userbot.call_executor import CallExecutor
from app.userbot.source_handler import apply_rewrite_rules


class _FakeSessionManager:
    def __init__(self, client):
        self._client = client

    def get_client(self):
        return self._client


class _FakeClient:
    def __init__(self):
        self.sent_calls = []

    async def send_message(self, entity, message, file=None, parse_mode=None, link_preview=None, reply_to=None):
        self.sent_calls.append(
            {
                "kind": "message",
                "entity": entity,
                "message": message,
                "file": file,
                "parse_mode": parse_mode,
                "reply_to": reply_to,
            }
        )
        return SimpleNamespace(id=123)

    async def send_file(self, entity, file, caption=None, parse_mode=None, reply_to=None):
        self.sent_calls.append(
            {
                "kind": "file",
                "entity": entity,
                "message": caption,
                "file": file,
                "parse_mode": parse_mode,
                "reply_to": reply_to,
            }
        )
        return SimpleNamespace(id=124)


@pytest.mark.asyncio
async def test_call_executor_uses_plain_text_for_copied_messages():
    client = _FakeClient()
    session_manager = _FakeSessionManager(client)
    executor = CallExecutor(userbot_id=42, session_manager=session_manager)

    executor._collect_message_media = AsyncMock(return_value=["media_object"])

    result = await executor.send_call_message(
        target_chat_id=-1001,
        message="hello_world",
        token_address="MSG-1-1",
        source_chat_id=-2002,
        source_message_id=77,
        copy_media=True,
        parse_mode=None,
    )

    assert result["success"] is True
    first_call = client.sent_calls[0]
    assert first_call["kind"] == "file"
    assert first_call["parse_mode"] is None
    assert first_call["file"] == "media_object"


@pytest.mark.asyncio
async def test_call_executor_defaults_to_markdown():
    client = _FakeClient()
    session_manager = _FakeSessionManager(client)
    executor = CallExecutor(userbot_id=99, session_manager=session_manager)

    result = await executor.send_call_message(
        target_chat_id=-3003,
        message="*bold*",
        token_address="MSG-2-2",
    )

    assert result["success"] is True
    assert client.sent_calls[0]["parse_mode"] == "md"
    assert client.sent_calls[0]["file"] is None


@pytest.mark.asyncio
async def test_call_executor_uses_embedded_media_payloads():
    client = _FakeClient()
    session_manager = _FakeSessionManager(client)
    executor = CallExecutor(userbot_id=77, session_manager=session_manager)

    buffer = BytesIO(b"fake-image-bytes")
    buffer.name = "image.jpg"

    result = await executor.send_call_message(
        target_chat_id=-4004,
        message="with media",
        token_address="MSG-3-3",
        media_bundle_override=[buffer],
        parse_mode=None,
    )

    assert result["success"] is True
    call = client.sent_calls[0]
    assert call["kind"] == "file"
    assert call["file"] is buffer


def test_apply_rewrite_rules_handles_replacements():
    text, changed = apply_rewrite_rules(
        "Visit @news_crypto at x.com",  # original
        [
            {"source": "@news_crypto", "target": "@coreati"},
            {"source": "x.com", "target": "ape.com"},
        ],
    )

    assert changed is True
    assert text == "Visit @coreati at ape.com"


def test_apply_rewrite_rules_noop_when_no_matches():
    original = "No replacements here"
    text, changed = apply_rewrite_rules(original, [])

    assert changed is False
    assert text == original
