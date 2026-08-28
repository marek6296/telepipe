"""V poloautomate sa chat neotvára, kým majiteľ neodpíše.

Marek: „mam to nastavene na poloautomaticky mod a ono furt ked napise niekto
tak nam to otvori tu jeho spravu takze dostane videne a ja nechcem davat to
videne ludom … aby videne som daval az ked mu budem chciet odpisat."

`_reconcile` ťahá `GET /chats/{uuid}/messages`. V poloautomate bežal pri KAŽDEJ
prichádzajúcej správe — teda ešte pred tým, než sa majiteľ vôbec rozhodol, či
odpovie. Presunuli sme ho za odoslanie (`_dobehni`): odoslaním sa videné dá tak
či tak, takže tam už čítanie nič nepokazí.

Kým majiteľ rozhoduje, stačí správa z webhooku. Že sa tá istá neskôr stiahne aj
so svojím uuid, rieši `texty_bez_uuid` v `fvsync.missing`.
"""
from __future__ import annotations

import inspect
import re

import fanvue_agent


class _Db:
    def __init__(self):
        self.spravy = []
        self.patche = []

    async def add_message(self, uuid, role, text, ref=""):
        self.spravy.append((role, text))

    async def fan(self, uuid):
        return {"msg_count": 3}

    async def update_fan(self, uuid, patch):
        self.patche.append(patch)

    async def record_send(self, *a, **kw):
        pass

    async def settings(self):
        return {}

    async def known_message_uuids(self, uuid):
        return set()

    async def texty_bez_uuid(self, uuid):
        return set()

    async def add_messages(self, uuid, rows):
        pass


class _Api:
    def __init__(self):
        self.citania = []
        self.odoslane = []

    async def send(self, uuid, text, *a, **kw):
        self.odoslane.append(text)
        return "msg-1"

    async def chat_messages(self, uuid, limit=30):
        self.citania.append(uuid)
        return []


def _agent():
    a = fanvue_agent.FanvueAgent.__new__(fanvue_agent.FanvueAgent)
    a._db = _Db()
    a._api = _Api()
    a._llm = None
    a._control = None
    return a


class TestVideneAzPriOdpovedi:
    async def test_odoslanie_textu_dobehne_chat(self):
        """Až tu — vtedy videné aj tak dáva samotné odoslanie."""
        a = _agent()
        assert await a.deliver_text("fan-1", "ahoj") is True
        assert a._api.citania == ["fan-1"]

    async def test_odoslanie_fotky_dobehne_chat(self):
        a = _agent()
        assert await a.deliver_photo("fan-1", "media-1", "caption") is True
        assert a._api.citania == ["fan-1"]

    async def test_dobehnutie_nezhodi_odoslanie(self):
        """Odpoveď je odoslaná — to je podstatné, zvyšok je bonus."""
        a = _agent()

        async def zlyha(*args, **kwargs):
            raise RuntimeError("Fanvue je dole")

        a._api.chat_messages = zlyha
        assert await a.deliver_text("fan-1", "ahoj") is True


class TestSemiChatNeotvara:
    """Zdrojová poistka: keby niekto `_reconcile` vrátil pred rozhodnutie
    o režime, videné by sa začalo dávať znova a v testoch by to nebolo vidno."""

    def _telo_reply(self) -> str:
        src = inspect.getsource(fanvue_agent.FanvueAgent._reply)
        return src

    def test_reconcile_je_az_za_kontrolou_semi(self):
        telo = self._telo_reply()
        assert "if semi:" in telo
        assert "elif not await self._reconcile" in telo, (
            "zosúladenie musí byť vo vetve, ktorá sa v semi NEVYKONÁ"
        )
        # Hľadá sa VOLANIE, nie zmienka — `_reconcile` je aj v komentári nad ním.
        i_semi = telo.index("if semi:")
        i_rec = telo.index("await self._reconcile(")
        assert i_semi < i_rec, "kontrola režimu musí byť PRED zosúladením"

    def test_v_semi_sa_sprava_ulozi_z_webhooku(self):
        telo = self._telo_reply()
        i = telo.index("if semi:")
        assert "add_message" in telo[i : i + 300]

    def test_chat_sa_cita_len_z_reconcile(self):
        """Keby pribudlo druhé miesto, ktoré ťahá správy, videné by unikalo."""
        src = inspect.getsource(fanvue_agent)
        volania = []
        aktualna = ""
        for line in src.splitlines():
            m = re.match(r"    async def (\w+)", line)
            if m:
                aktualna = m.group(1)
            if "self._api.chat_messages(" in line:
                volania.append(aktualna)
        assert volania == ["_reconcile"], f"správy chatu ťahá aj: {volania}"

    def test_dobehnutie_volaju_obe_dorucenia(self):
        src = inspect.getsource(fanvue_agent)
        assert src.count("await self._dobehni(") == 2
