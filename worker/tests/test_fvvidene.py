"""V poloautomate sa chat číta, ale „videné" fanúšikovi nesvieti.

Marek: „mam to nastavene na poloautomaticky mod a ono furt ked napise niekto
tak nam to otvori tu jeho spravu takze dostane videne a ja nechcem davat to
videne ludom … aby videne som daval az ked mu budem chciet odpisat."

PRVÉ RIEŠENIE BOLO PRIHRUBÉ. Zosúladenie (`_reconcile`) sa v semi vyplo úplne
a do pamäte šla len správa z webhooku. Lenže Fanvue webhookom NEPOSIELA to, čo
majiteľ odpíše priamo z ich appky — a tak v pamäti aj na karte chýbala celá
jedna strana rozhovoru. Naostro: 24 jeho správ za sebou a ani jedna jej, hoci
v chate na Fanvue medzi nimi odpovedal.

TERAZ. `GET /chats/{uuid}/messages` má parameter `markAsRead` (predvolene
`true`). V poloautomate ide na `false`: chat vidíme celý, videné sa nedáva.
Overené naostro proti Fanvue — chat s `unreadMessagesCount = 2` ostal po
stiahnutí dvadsiatich správ naďalej na dvoch.

Tesne pred odoslaním (`deliver_text` / `deliver_photo`) sa explicitne
potvrdí prečítanie; následné dobehnutie už nové správy neoznačuje ako videné.
"""
from __future__ import annotations

import inspect

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

    async def chat_messages(self, uuid, limit=30, mark_read=True):
        self.citania.append((uuid, mark_read))
        return []


def _agent():
    a = fanvue_agent.FanvueAgent.__new__(fanvue_agent.FanvueAgent)
    a._db = _Db()
    a._api = _Api()
    a._llm = None
    a._control = None
    return a


class TestOdoslaniePotvrdiPrecitanie:
    async def test_odoslanie_textu_dobehne_chat(self):
        """Seen pred send, následná synchronizácia nechá nové správy neprečítané."""
        a = _agent()
        assert await a.deliver_text("fan-1", "ahoj") is True
        assert a._api.citania == [("fan-1", True), ("fan-1", False)]

    async def test_odoslanie_fotky_dobehne_chat(self):
        a = _agent()
        assert await a.deliver_photo("fan-1", "media-1", "caption") is True
        assert a._api.citania == [("fan-1", True), ("fan-1", False)]

    async def test_dobehnutie_nezhodi_odoslanie(self):
        """Odpoveď je odoslaná — to je podstatné, zvyšok je bonus."""
        a = _agent()

        async def zlyha(*args, **kwargs):
            raise RuntimeError("Fanvue je dole")

        a._api.chat_messages = zlyha
        assert await a.deliver_text("fan-1", "ahoj") is True


class TestSemiCitaBezVideneho:
    async def test_reconcile_posiela_prepinac_dalej(self):
        a = _agent()
        assert await a._reconcile({"uuid": "fan-1", "text": "hey"}, {}, mark_read=False)
        assert a._api.citania == [("fan-1", False)]

    async def test_predvolene_sa_videne_nedava(self):
        """Aj Auto má pred odoslaním generovanie a čakanie."""
        a = _agent()
        assert await a._reconcile({"uuid": "fan-1", "text": "hey"}, {})
        assert a._api.citania == [("fan-1", False)]

    def test_dobehnutie_volaju_obe_dorucenia(self):
        src = inspect.getsource(fanvue_agent)
        assert src.count("await self._dobehni(") == 2


class TestPrepinacIdeDoFanvue:
    def test_parameter_sa_posiela_vzdy(self):
        """Fanvue má `markAsRead` predvolene `true`. Keby sme ho poslali len
        pri `false`, stačila by zmena na ich strane a videné by unikalo."""
        src = inspect.getsource(__import__("fanvue_api").Fanvue.chat_messages)
        assert '"markAsRead": "true" if mark_read else "false"' in src
