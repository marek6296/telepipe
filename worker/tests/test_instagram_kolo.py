"""Celé kolo Instagram agenta s falošným API a falošnou databázou.

Overuje to, čo sa na jednotlivých funkciách overiť nedá: že sa odpovie práve
raz, že sa neodpovie po okne, že tá istá správa nespôsobí druhú odpoveď — a
hlavne, že do Instagramu neodíde nič, čo tam nesmie.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import instagram_agent
import instagram_api as api


def _teraz(minus_h=0):
    return (datetime.now(timezone.utc) - timedelta(hours=minus_h)).isoformat()


MOJE_ID = "17841400000000000"


class FakeDb:
    def __init__(self, **nastavenia):
        self.nastavenia = {
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

    async def persona(self):
        return {
            "name": "Simona", "age": 27, "city": "LA", "backstory": "x" * 60,
            "tone": "hravá", "msg_style": "krátke", "boundaries": "", "funnel_rules": "",
            "cta_link": "https://fanvue.com/simona", "extra_rules": "", "examples": "",
            "languages": "", "lang_primary": "en", "lang_extra": [],
        }

    async def behavior(self):
        return {"mode": "real"}

    async def user(self, igsid):
        return self.users.get(igsid)

    async def ensure_user(self, igsid, username=""):
        return self.users.setdefault(
            igsid,
            {"igsid": igsid, "username": username, "msg_count": 0, "pointed_count": 0,
             "ai_enabled": True, "human_takeover": False},
        )

    async def update_user(self, igsid, patch):
        self.patche.append((igsid, patch))
        self.users.setdefault(igsid, {}).update(patch)

    async def known_mids(self, igsid, limit=60):
        return {s["mid"] for s in self.spravy if s["igsid"] == igsid and s["mid"]}

    async def add_message(self, igsid, role, content, mid=""):
        self.spravy.append({"igsid": igsid, "role": role, "content": content, "mid": mid})

    async def history(self, igsid, limit=16):
        return [
            {"role": s["role"], "content": s["content"]}
            for s in self.spravy if s["igsid"] == igsid
        ][-limit:]


class FakeLlm:
    def __init__(self, odpoved="hey you 😄"):
        self.odpoved = odpoved
        self.prompty = []

    async def reply(self, system, history):
        self.prompty.append(system)
        return self.odpoved


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

    def fake_konverzacie(token, limit=25):
        return konverzacie

    def fake_posli(token, igsid, text):
        odoslane.append((igsid, text))
        return {"message_id": "odoslana-1"}

    monkeypatch.setattr(api, "konverzacie", fake_konverzacie)
    monkeypatch.setattr(api, "posli_text", fake_posli)

    agent = instagram_agent.InstagramAgent(db, llm)
    asyncio.run(agent._kolo())
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
        class FakeControl:
            def __init__(self):
                self.spravy = []

            async def notify(self, text):
                self.spravy.append(text)

        db, llm = FakeDb(reply_mode="semi"), FakeLlm()
        control = FakeControl()
        odoslane = []

        def fake_konverzacie(token, limit=25):
            return [_konverzacia()]

        def fake_posli(token, igsid, text):
            odoslane.append(text)
            return {}

        monkeypatch.setattr(api, "konverzacie", fake_konverzacie)
        monkeypatch.setattr(api, "posli_text", fake_posli)
        agent = instagram_agent.InstagramAgent(db, llm, control=control)
        asyncio.run(agent._kolo())

        assert odoslane == [], "v semi režime sa neodosiela"
        assert control.spravy, "návrh musí prísť majiteľovi"


class TestNicZakazaneNeodide:
    """Aj keď to model napíše, von to nesmie ísť."""

    def test_odkaz_na_fanvue_sa_odstrani(self, monkeypatch):
        db = FakeDb()
        llm = FakeLlm("nájdeš ma na https://fanvue.com/simona babe")
        odoslane = _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert odoslane, "odpoveď má odísť"
        assert "fanvue.com" not in odoslane[0][1]

    def test_akykolvek_odkaz_sa_odstrani(self, monkeypatch):
        db = FakeDb()
        llm = FakeLlm("pozri https://linkovne.com/simona")
        odoslane = _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert "http" not in odoslane[0][1]

    def test_dlha_odpoved_sa_oreze(self, monkeypatch):
        db = FakeDb()
        llm = FakeLlm("slovo " * 500)
        odoslane = _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert len(odoslane[0][1].encode("utf-8")) <= api.MAX_BAJTOV

    def test_prompt_zakazuje_platene_platformy(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert "NIKDY nespomeň" in llm.prompty[0]
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
        llm = FakeLlm("napis mi na simona_here, tam sa pobavime")
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        posledny = db.users["999"]
        assert posledny.get("pointed_count") == 1

    def test_bezna_odpoved_sa_nerata(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm("hey you 😄")
        _spusti(db, llm, [_konverzacia()], monkeypatch)
        assert db.users["999"].get("pointed_count", 0) == 0


class TestPadyNezhodiaAgenta:
    def test_pad_api_len_zapise_chybu(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()

        def rozbite(token, limit=25):
            raise api.InstagramError("token expired", kod=190)

        monkeypatch.setattr(api, "konverzacie", rozbite)
        agent = instagram_agent.InstagramAgent(db, llm)
        asyncio.run(agent._kolo())
        assert any("poll_error" in u for u in db.ulozene)

    def test_pad_odoslania_nezhodi_kolo(self, monkeypatch):
        db, llm = FakeDb(), FakeLlm()

        def rozbite_poslanie(token, igsid, text):
            raise api.InstagramError("rate limited", kod=4)

        monkeypatch.setattr(api, "konverzacie", lambda token, limit=25: [_konverzacia()])
        monkeypatch.setattr(api, "posli_text", rozbite_poslanie)
        agent = instagram_agent.InstagramAgent(db, llm)
        asyncio.run(agent._kolo())  # nesmie hodiť
