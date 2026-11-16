from urllib.parse import urlparse
import pytest
import instagram_api as api


def test_unified_uses_instagram_id_not_system_user(monkeypatch):
    calls = []
    monkeypatch.setattr(api, '_volaj', lambda url, data=None: calls.append((url, data)) or {'data': []})
    api.konverzacie('test', account_id='ig123')
    api.posli_text('test', 'fan123', 'Hello', account_id='ig123')
    api.prispevky_s_komentarmi('test', account_id='ig123')
    for (url, _), path in zip(calls, ['conversations', 'messages', 'media']):
        parsed = urlparse(url)
        assert parsed.netloc == 'graph.facebook.com'
        assert parsed.path == '/v27.0/ig123/' + path
    assert calls[1][1]['recipient']['id'] == 'fan123'


def test_missing_instagram_id_cannot_fall_back_to_me():
    with pytest.raises(TypeError):
        api.konverzacie('test')


def test_revoked_access_disconnects_instead_of_polling_forever(monkeypatch):
    import asyncio
    from instagram_agent import InstagramAgent
    class Db:
        changes = []
        async def settings(self):
            return {"connected": True, "enabled": True, "reply_mode": "auto", "access_token": "test", "ig_user_id": "123"}
        async def save(self, patch):
            self.changes.append(patch)
    def revoked(*args, **kwargs):
        raise api.InstagramError("expired", kod=190)
    monkeypatch.setattr(api, "konverzacie", revoked)
    db = Db()
    assert asyncio.run(InstagramAgent(db, None)._kolo()) is False
    assert db.changes[-1]["connected"] is False
