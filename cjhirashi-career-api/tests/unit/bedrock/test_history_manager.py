"""Unit tests for history_manager.append_message - must accept a plain
conversation id (str), never an ORM object whose attributes can expire mid-turn
(MissingGreenlet regression, see state.md 2026-09-04)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.bedrock import history_manager


@pytest.mark.requisito("RF-002")
async def test_append_message_accepts_plain_id():
    db = AsyncMock()
    db.add = MagicMock()

    await history_manager.append_message(db, "conv-123", "user", "hola")

    db.add.assert_called_once()
    (message,), _ = db.add.call_args
    assert message.conversation_id == "conv-123"
    assert message.role == "user"
    assert message.content == "hola"
    db.commit.assert_awaited_once()
