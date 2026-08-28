"""Poloautomatický režim platí AJ na poďakovanie a privítanie.

PREČO. Marek má Fanvue v režime `semi` a schvaľuje každú odpoveď — a modelka
mu aj tak sama odpisovala, keď si niekto niečo kúpil. Dôvod: `reply_mode` sa
kontroloval len v `_reply`, teda na ceste od PRICHÁDZAJÚCEJ SPRÁVY.
Poďakovanie a privítanie chodia z webhooku o platbe a o novom
predplatiteľovi, takže tú bránu obišli úplne.

Rovnaká diera platila pre `off`: režim „nepíš" písal.
"""
from __future__ import annotations

import fanvue_agent
import fvflow


class _Db:
    def __init__(self, row):
        self.row = dict(row)
        self.patches = []
        self.spravy = []

    async def persona(self):
        return {"name": "Simona", "backstory": "x", "msg_style": "krátko"}

    async def behavior(self):
        return {}

    async def history(self, uuid):
        return [{"role": "user", "content": "hey"}]

    async def fan(self, uuid):
        return dict(self.row)

    async def upsert_fan(self, uuid, patch):
        self.row.update(patch)

    async def update_fan(self, uuid, patch):
        self.patches.append(patch)
        self.row.update(patch)

    async def settings(self):
        return {}

    async def add_message(self, uuid, role, text, ref=""):
        self.spravy.append(text)


class _Api:
    def __init__(self):
        self.sent = []

    async def send(self, uuid, text, *a, **kw):
        self.sent.append(text)
        return "msg-1"


class _Llm:
    async def reply(self, prompt, history):
        return "thanks babe 😘"

    async def suggest(self, prompt, history, angles=None, **kw):
        return ["a", "b", "c"]


class _Control:
    def __init__(self, ok=True):
        self.ok = ok
        self.karty = []

    async def post_approval(self, **kw):
        self.karty.append(kw)
        return self.ok


def _agent(row=None, control=None, api=None):
    a = fanvue_agent.FanvueAgent.__new__(fanvue_agent.FanvueAgent)
    a._db = _Db(row if row is not None else {"ai_enabled": True})
    a._api = api or _Api()
    a._llm = _Llm()
    a._control = control if control is not None else _Control()
    return a


FAN = {"uuid": "fan-uuid-1", "name": "Colin"}


class TestPodakovanieZaNakup:
    """„Ked kupi niekto nieco" — presne to Marek nahlásil."""

    async def test_semi_posle_kartu_a_nie_spravu(self):
        a = _agent()
        await a._thank(FAN, {"ai_enabled": True}, {"reply_mode": "semi"}, 3099, 1)
        assert a._api.sent == [], "v semi nesmie odpísať sama"
        assert len(a._control.karty) == 1

    async def test_off_nenapise_ani_kartu(self):
        a = _agent()
        await a._thank(FAN, {"ai_enabled": True}, {"reply_mode": "off"}, 3099, 1)
        assert a._api.sent == []
        assert a._control.karty == []

    async def test_auto_odpise_ako_predtym(self):
        """Toto je pôvodné správanie a musí ostať nedotknuté."""
        a = _agent()
        await a._thank(FAN, {"ai_enabled": True}, {"reply_mode": "auto"}, 3099, 1)
        assert a._api.sent == ["thanks babe 😘"]
        assert a._control.karty == []

    async def test_chybajuci_rezim_je_auto(self):
        a = _agent()
        await a._thank(FAN, {"ai_enabled": True}, {}, 500, 1)
        assert a._api.sent == ["thanks babe 😘"]

    async def test_karta_povie_za_co_to_je(self):
        a = _agent()
        await a._thank(FAN, {"ai_enabled": True}, {"reply_mode": "semi"}, 3099, 1)
        nahlad = a._control.karty[0]["incoming_preview"]
        assert "$30.99" in nahlad, "majiteľ musí vidieť, prečo karta prišla"

    async def test_zapise_sa_az_po_odoslanej_karte(self):
        """Inak by človek ostal bez vďaky aj bez karty."""
        a = _agent(control=_Control(ok=False))
        await a._thank(FAN, {"ai_enabled": True}, {"reply_mode": "semi"}, 500, 1)
        assert a._db.patches == []

    async def test_po_odoslanej_karte_sa_neopakuje(self):
        a = _agent()
        await a._thank(FAN, {"ai_enabled": True}, {"reply_mode": "semi"}, 500, 1)
        assert "last_thanks_at" in a._db.patches[0]


class TestPrivitanieNovehoPredplatitela:
    async def test_semi_posle_kartu_a_nie_spravu(self):
        a = _agent()
        await a._greet({"payload": {"data": {"user": FAN}}}, {"reply_mode": "semi"})
        assert a._api.sent == []
        assert len(a._control.karty) == 1

    async def test_off_mlci(self):
        a = _agent()
        await a._greet({"payload": {"data": {"user": FAN}}}, {"reply_mode": "off"})
        assert a._api.sent == []
        assert a._control.karty == []

    async def test_auto_privita_ako_predtym(self):
        a = _agent()
        await a._greet({"payload": {"data": {"user": FAN}}}, {"reply_mode": "auto"})
        assert a._api.sent == ["thanks babe 😘"]

    async def test_vypnute_ai_neprivita(self):
        """Doteraz bola jediná brána `greeted` — ani toto sa nekontrolovalo."""
        a = _agent(row={"ai_enabled": False})
        await a._greet({"payload": {"data": {"user": FAN}}}, {"reply_mode": "auto"})
        assert a._api.sent == []

    async def test_prevzaty_chat_neprivita(self):
        a = _agent(row={"ai_enabled": True, "human_takeover": True})
        await a._greet({"payload": {"data": {"user": FAN}}}, {"reply_mode": "auto"})
        assert a._api.sent == []

    async def test_greeted_az_po_odoslanej_karte(self):
        a = _agent(control=_Control(ok=False))
        await a._greet({"payload": {"data": {"user": FAN}}}, {"reply_mode": "semi"})
        assert a._db.patches == []


class TestPopisyKariet:
    def test_prvy_nakup(self):
        out = fvflow.popis_nakupu(3099, 1)
        assert "$30.99" in out and "first purchase" in out

    def test_dalsi_nakup(self):
        assert "purchase #3" in fvflow.popis_nakupu(500, 3)

    def test_bez_sumy_nepadne(self):
        assert "something" in fvflow.popis_nakupu(0, 1)

    def test_predplatne(self):
        assert "subscribed" in fvflow.POPIS_PREDPLATNEHO


class TestZiadnaInaCestaNeobchadza:
    def test_vsetky_odoslania_su_zname(self):
        """Keby pribudla šiesta cesta k `_api.send`, tento test na ňu upozorní.

        `deliver_text`/`deliver_photo` volá control bot AŽ PO schválení, tie
        bránu mať nesmú — ostatné tri áno.
        """
        import inspect
        import re

        src = inspect.getsource(fanvue_agent)
        funkcie = []
        aktualna = ""
        for line in src.splitlines():
            m = re.match(r"    async def (\w+)", line)
            if m:
                aktualna = m.group(1)
            if "await self._api.send(" in line:
                funkcie.append(aktualna)
        assert sorted(funkcie) == [
            "_greet", "_reply", "_thank", "deliver_photo", "deliver_text",
        ], f"pribudla nová cesta k odoslaniu: {funkcie}"
