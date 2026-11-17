from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from telethon.tl import types

from control_bot import ControlBot


def bot(owner=42, token='123:private-token'):
    cfg = SimpleNamespace(model_id='10000000-0000-0000-0000-000000000001',
                          owner_chat_id=owner, control_bot_token=token)
    client = AsyncMock()
    return ControlBot(cfg, SimpleNamespace(), client, notifications_only=True), client


async def test_menu_uses_exact_paired_chat_and_mini_bot_hint(monkeypatch):
    control, client = bot()
    calls = []
    async def post(_self, url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'ok': True})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    await control.nastav_mini_menu()
    assert len(calls) == 1
    assert calls[0][1]['json'] == {'chat_id': 42, 'menu_button': {
        'type': 'web_app', 'text': 'Social sites',
        'web_app': {'url': 'https://telepipe.me/mini?bot=10000000-0000-0000-0000-000000000001'},
    }}
    client.send_message.assert_not_awaited()


@pytest.mark.parametrize('owner,token', [(0, 'secret'), (42, '')])
async def test_unpaired_or_disconnected_menu_makes_no_api_call(owner, token, monkeypatch):
    control, _ = bot(owner, token)
    post = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    await control.nastav_mini_menu()
    post.assert_not_awaited()


async def test_bot_token_never_leaks_from_menu_error(monkeypatch, caplog):
    control, _ = bot()
    async def post(_self, url, **_kwargs):
        raise httpx.ConnectError('failed '+url)
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    await control.nastav_mini_menu()
    assert 'private-token' not in caplog.text
    assert 'api.telegram.org' not in caplog.text
    assert 'ConnectError' in caplog.text


async def test_notification_opens_contact_inside_mini_app():
    control, client = bot()
    await control.notify_inbound({'channel':'telegram','external_id':'123','owner_chat_id':42,
                                  'display_name':'Fan','preview':'Hello','message_count':1})
    button = client.send_message.await_args.kwargs['buttons'][0][0]
    assert isinstance(button, types.KeyboardButtonWebView)
    assert button.url.endswith('&contact=telegram%3A123')
    assert '/mini?bot=' in button.url
