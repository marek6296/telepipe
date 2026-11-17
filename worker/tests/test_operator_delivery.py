from unittest.mock import AsyncMock
import pytest
from operator_delivery import composition_pause

@pytest.mark.asyncio
@pytest.mark.parametrize("text",["hi","hello "*20,"x"*12000])
async def test_seen_pause_is_bounded_and_length_dependent(text,monkeypatch):
    import operator_delivery
    sleep=AsyncMock()
    monkeypatch.setattr(operator_delivery.asyncio,"sleep",sleep)
    await composition_pause(text)
    seconds=sleep.await_args.args[0]
    assert 1.5 <= seconds <= 22
    if len(text)>100: assert seconds>5
