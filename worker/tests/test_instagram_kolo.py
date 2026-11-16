"""Celé kolo Instagram agenta s falošným API a falošnou databázou.

Overuje to, čo sa na jednotlivých funkciách overiť nedá: že sa odpovie práve
raz, že sa neodpovie po okne, že tá istá správa nespôsobí druhú odpoveď — a
hlavne, že do Instagramu neodíde nič, čo tam nesmie.
"""
import asyncio
from unittest.mock import AsyncMock
import den
from datetime import datetime, timedelta, timezone

import instagram_agent
import instagram_api as api


def _teraz(minus_h=0):
    return (datetime.now(timezone.utc) - timedelta(hours=minus_h)).isoformat()


MOJE_ID = "17841400000000000"


class FakeDb:
    def __init__(self, **nastavenia):
        self.model_id = "model"
        self.hub = AsyncMock()
        self.hub.restrictions.return_value = {}
        self.hub.context.return_value = ""
        self.hub.linked.return_value = []
        self.hub.day.return_value = (den.Blok(0, 2880, "home", "relaxing", 1), "relaxed")
        self.hub.mood_prompt = lambda mood: "stable mood"
        self.queue = {}
        self.processed = set()
        self.nastavenia = {
            "sync_completed_at": _teraz(48),
            "sync_started_at": _teraz(48),
            "replies_started_at": _teraz(24),
            "connected": True,
            "enabled": True,
            "access_token": "token",
            "reply_mode": "auto",
            "ig_user_id": MOJE_ID,
            "funnel_target": "telegram",
            "telegram_handle": "simona_here",
            "heat": "mild",
            **nastavenia,
        }
        self.users = {}
        self.spravy = []
        self.patche = []
        self.ulozene = []

    async def settings(self):
        return dict(self.nastavenia)

    async def save(self, patch):
        self.ulozene.append(patch)
        self.nastavenia.update(patch)

    async def persona(self):
        return {
            "name": "Simona", "age": 27, "city": "LA", "backstory": "x" * 60,
            "tone": "hravá", "msg_style": "krátke", "boundaries": "", "funnel_rules": "",
            "cta_link": "https://fanvue.com/simona", "extra_rules": "", "examples": "",
            "languages": "", "lang_primary": "en", "lang_extra": [],
        }

    async def behavior(self):
        return {"mode": "real", "active_start_min": 0, "active_end_min": 0}

    async def user(self, igsid):
        return self.users.get(igsid)

    async def ensure_user(self, igsid, username=""):
        return self.users.setdefault(
            igsid,
            {"igsid": igsid, "username": username, "msg_count": 0, "pointed_count": 0,
             "age_state": "adult_self_declared", "ai_enabled": True, "human_takeover": False},
        )

    async def update_user(self, igsid, patch):
        self.patche.append((igsid, patch))
        self.users.setdefault(igsid, {}).update(patch)

    async def known_mids(self, igsid, limit=60):
        return {s["mid"] for s in self.spravy if s["igsid"] == igsid and s["mid"]}

    async def add_message(self, igsid, role, content, mid="", **kwargs):
        self.spravy.append({"igsid": igsid, "role": role, "content": content, "mid": mid})

    async def history(self, igsid, limit=16):
        return [
            {"role": s["role"], "content": s["content"]}
            for s in self.spravy if s["igsid"] == igsid
        ][-limit:]

    async def recent_chats(self, limit=10):
        return [dict(u) for u in self.users.values()][:limit]

    async def handled_comments(self, ids):
        return {k["comment_id"] for k in getattr(self, "komentare", []) if k["comment_id"] in ids}

    async def save_comment(self, row):
        self.__dict__.setdefault("komentare", []).append(dict(row))

    async def processed_mids(self, igsid):
        return self.processed

    async def mark_message_effects(self, mid):
        self.processed.add(mid)

    async def schedule(self):
        return {}

    async def sfw_photo(self):
        return None

    async def cancel_actions(self, igsid='', reason='channel_off'):
        for a in self.queue.values():
            if (not igsid or a['igsid'] == igsid) and a['state'] in ('pending','ready','leased','approval'):
                a.update(state='cancelled', reason=reason)

    async def actions(self, **params):
        rows = list(self.queue.values())
        for key, value in params.items():
            if value.startswith('eq.'):
                expected = value[3:]
                rows = [r for r in rows if str(r.get(key, '')).lower() == expected.lower()]
            elif value == 'not.is.null':
                rows = [r for r in rows if r.get(key) is not None]
            elif value.startswith('in.('):
                rows = [r for r in rows if r.get(key) in value[4:-1].split(',')]
        return [dict(r) for r in rows]

    async def action(self, id):
        return dict(self.queue[id]) if id in self.queue else None

    async def change_action(self, action, patch, state='leased'):
        a = self.queue[action['id']]
        if a['state'] != state:
            return []
        a.update(patch)
        return [dict(a)]

    async def rpc(self, name, **args):
        if name == 'enqueue':
            for a in self.queue.values():
                if a['dedupe_key'] == args['key']:
                    return dict(a)
            id = str(len(self.queue)+1)
            self.queue[id] = {**args, 'id': id, 'dedupe_key': args['key'], 'target_id': args['target'],
                'state': 'pending', 'due_at': args['due'], 'expires_at': args['expires'], 'text': ''}
            return dict(self.queue[id])
        if name == 'claim':
            for a in self.queue.values():
                if a['state'] in ('pending','ready') and datetime.fromisoformat(a['due_at']) <= datetime.now(timezone.utc):
                    a.update(state='leased',lease_token='lease')
                    return dict(a)
            return None
        if name == 'reserve':
            a = self.queue[args['action']]
            user = self.users.get(a['igsid'], {})
            if self.nastavenia['reply_mode'] == 'off' or not self.nastavenia['enabled'] or user.get('human_takeover'):
                a['state'] = 'blocked'
                return {'ok': False, 'reason': 'off'}
            a.update(state='sending', text=args['text'], contains_link=args['link'], contains_reminder=args['reminder'], reserved_at=_teraz())
            return {'ok': True}
        if name == 'finish':
            a = self.queue[args['action']]
            a.update(state='blocked' if args['outcome']=='failed' else args['outcome'], provider_id=args.get('provider',''))
            if args['outcome']=='sent' and a['igsid'] in self.users:
                self.users[a['igsid']]['msg_count'] += 1
                if a.get('contains_link'):
                    self.users[a['igsid']]['link_sent_at'] = _teraz()
            return True
        if name == 'release_unsent':
            a = self.queue[args['action']]
            if a['state'] != 'sending' or a['lease_token'] != args['lease']:
                return False
            a.update(state='pending',reserved_at=None,lease_token=None,reason=args['reason'])
            return True
        if name == 'record_manual':
            return None
        raise AssertionError(name)


def tick(agent, db):
    """Explicitly advance queued due times; production never skips the delay."""
    for a in db.queue.values():
        if a['state'] in ('pending','ready'):
            a['due_at'] = _teraz(1)
    asyncio.run(agent._delivery.process_one(db.nastavenia))


def mock_threads(monkeypatch, threads):
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **k: {'success': True})
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': threads, 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: threads[0])


class FakeLlm:
    def __init__(self, odpoved="hey you 😄", navrhy=None):
        self.odpoved = odpoved
        self.navrhy = navrhy if navrhy is not None else ["návrh jeden", "návrh dva", "návrh tri"]
        self.prompty = []
        self.suggest_volania = []

    async def reply(self, system, history):
        self.prompty.append(system)
        return self.odpoved

    async def suggest(self, system, history, n=3, angles=None, seed="", model=""):
        self.prompty.append(system)
        self.suggest_volania.append({"angles": angles, "seed": seed})
        return list(self.navrhy)


class FakeControl:
    """Control bot: zbiera schvaľovacie karty a registrovaných odosielateľov."""

    def __init__(self, ok=True):
        self.karty = []
        self.senders = {}
        self.ok = ok
        self.recovered_with_senders = []

    async def recover_cards(self):
        self.recovered_with_senders.append(set(self.senders))

    async def post_approval(self, **karta):
        self.karty.append(karta)
        return self.ok

    def register_sender(self, channel, sender):
        self.senders[channel] = sender


def _konverzacia(text="hi", pred_h=0, mid="m1"):
    return {
        "id": "conv-1",
        "updated_time": _teraz(pred_h),
        "messages": {"data": [
            {"id": mid, "from": {"id": "999", "username": "fan"},
             "message": text, "created_time": _teraz(pred_h)},
        ]},
    }


def _spusti(db, llm, konverzacie, monkeypatch, odoslane=None):
    odoslane = odoslane if odoslane is not None else []

    def fake_konverzacie(token, limit=25, **kwargs):
        return konverzacie

    def fake_posli(token, igsid, text, **kwargs):
        odoslane.append((igsid, text))
        return {"message_id": "odoslana-1"}

    mock_threads(monkeypatch, konverzacie)
    monkeypatch.setattr(api, "posli_text", fake_posli)

    agent = instagram_agent.InstagramAgent(db, llm)
    asyncio.run(agent._kolo())
    tick(agent, db)
    return odoslane


class TestZakladneKolo:
    def test_odpovie_na_novu_spravu(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()
        odoslane = _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert len(odoslane) == 1
        assert odoslane[0][0] == "999"

    def test_odpoved_pristane_v_historii(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert [s["role"] for s in db.spravy] == ["user", "assistant"]

    def test_druhy_krat_na_tu_istu_spravu_neodpovie(self, monkeypatch):
        """Konverzácie sa ťahajú dokola — bez toho by odpisovala každých 45 s."""
        db, llm = FakeDb(), FakeLlm()
        konv = [_konverzacia()]
        odoslane = _spusti(db, llm, konv, monkeypatch)
        _spusti(db, llm, konv, monkeypatch, odoslane)
        assert len(odoslane) == 1

    def test_po_okne_neodpovie(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()
        odoslane = _spusti(db, llm, [_konverzacia(pred_h=30)], monkeypatch)
        assert odoslane == []

    def test_ked_je_posledne_slovo_jej_neodpovie(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()
        konv = _konverzacia()
        konv["messages"]["data"].insert(0, {
            "id": "m2", "from": {"id": MOJE_ID}, "message": "uz som odpisala",
            "created_time": _teraz(0),
        })
        assert _spusti(db, llm, [konv], monkeypatch) == []


class TestVypinace:
    def test_vypnuty_agent_mlci(self, monkeypatch):
        db, llm = FakeDb(enabled=False), FakeLlm()
        assert _spusti(db, llm, [_konverzacia()], monkeypatch) == []

    def test_nepripojeny_ucet_mlci(self, monkeypatch):
        db, llm = FakeDb(connected=False), FakeLlm()
        assert _spusti(db, llm, [_konverzacia()], monkeypatch) == []

    def test_rezim_off_mlci(self, monkeypatch):
        db, llm = FakeDb(reply_mode="off"), FakeLlm()
        assert _spusti(db, llm, [_konverzacia()], monkeypatch) == []

    def test_bez_tokenu_mlci(self, monkeypatch):
        db, llm = FakeDb(access_token=""), FakeLlm()
        assert _spusti(db, llm, [_konverzacia()], monkeypatch) == []

    def test_prevzaty_chat_mlci(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()
        db.users["999"] = {"igsid": "999", "human_takeover": True, "msg_count": 3,
                           "pointed_count": 0, "ai_enabled": True}
        assert _spusti(db, llm, [_konverzacia()], monkeypatch) == []

    def test_semi_rezim_neposiela_ale_navrhuje(self, monkeypatch):
        db, llm = FakeDb(reply_mode="semi"), FakeLlm()
        control = FakeControl()
        odoslane = []

        def fake_konverzacie(token, limit=25, **kwargs):
            return [_konverzacia()]

        def fake_posli(token, igsid, text, **kwargs):
            odoslane.append(text)
            return {}

        mock_threads(monkeypatch, [_konverzacia()])
        monkeypatch.setattr(api, "posli_text", fake_posli)
        agent = instagram_agent.InstagramAgent(db, llm, control=control)
        asyncio.run(agent._kolo())

        assert odoslane == [], "v semi režime sa neodosiela"
        tick(agent, db)
        assert control.karty, "návrh musí prísť majiteľovi ako karta"


class TestNicZakazaneNeodide:
    """Aj keď to model napíše, von to nesmie ísť."""

    def test_odkaz_na_fanvue_sa_odstrani(self, monkeypatch):
        db = FakeDb()
        llm = FakeLlm("nájdeš ma na https://fanvue.com/simona babe")
        odoslane = _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert not odoslane, "unsafe generated invitation is rejected"

    def test_akykolvek_odkaz_sa_odstrani(self, monkeypatch):
        db = FakeDb()
        llm = FakeLlm("pozri https://linkovne.com/simona")
        odoslane = _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert not odoslane

    def test_dlha_odpoved_sa_oreze(self, monkeypatch):
        db = FakeDb()
        llm = FakeLlm("slovo " * 500)
        odoslane = _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert len(odoslane[0][1].encode("utf-8")) <= api.MAX_BAJTOV

    def test_prompt_zakazuje_platene_platformy(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert "Never promote or name Fanvue" in llm.prompty[0]
        assert "ODKAZ JE TERAZ ZAKÁZANÝ" in llm.prompty[0]

    def test_prompt_ma_aj_ludsku_vrstvu(self, monkeypatch):
        """Instagram nie je iná osoba — je to tá istá na inom mieste."""
        db, llm = FakeDb(), FakeLlm()
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert "ČO PLATÍ NADO VŠETKÝM" in llm.prompty[0]
        assert "Simona" in llm.prompty[0]


class TestPozvanie:
    def test_spocita_ked_povie_telegram(self, monkeypatch):
        db = FakeDb()
        llm = FakeLlm("come say hi [[LINK]]")
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        posledny = db.users["999"]
        assert posledny.get("link_sent_at")

    def test_bezna_odpoved_sa_nerata(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm("hey you 😄")
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert db.users["999"].get("pointed_count", 0) == 0


class TestPadyNezhodiaAgenta:
    def test_pad_api_len_zapise_chybu(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()

        def rozbite(token, limit=25, **kwargs):
            raise api.InstagramError("token expired", kod=190)

        monkeypatch.setattr(api, "conversation_page", rozbite)
        agent = instagram_agent.InstagramAgent(db, llm)
        asyncio.run(agent._kolo())
        assert any("poll_error" in u for u in db.ulozene)

    def test_pad_odoslania_nezhodi_kolo(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()

        def rozbite_poslanie(token, igsid, text, **kwargs):
            raise api.InstagramError("rate limited", kod=4)

        mock_threads(monkeypatch, [_konverzacia()])
        monkeypatch.setattr(api, "posli_text", rozbite_poslanie)
        agent = instagram_agent.InstagramAgent(db, llm)
        asyncio.run(agent._kolo())  # nesmie hodiť
