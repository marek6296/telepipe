"""Uspatie na pár hodín — pauza, ktorá sa sama zobudí.

Ručná pauza (`ai_paused`) platí, kým ju niekto nevypne, a presne na to sa
zabúda: modelka mlčí deň, majiteľ nechápe prečo. Uspatie má koniec.
"""
from datetime import datetime, timedelta, timezone

import db as db_mod


class FakeTransport(db_mod.TenantDb):
    """Len `_get`/`_patch` — zvyšok triedy je ten pravý."""

    def __init__(self, row):
        self.row = dict(row)
        self.patches = []
        self.model_id = "m"

    async def _get(self, path, params):  # noqa: D102
        return [dict(self.row)]

    async def _patch(self, path, params, body):  # noqa: D102
        self.patches.append(body)
        self.row.update(body)


def _o(hodin):
    return (datetime.now(timezone.utc) + timedelta(hours=hodin)).isoformat()


class TestSpanok:
    async def _paused(self, row):
        return await FakeTransport(row).is_paused()

    def test_uspata_mlci(self):
        import asyncio

        assert asyncio.run(self._paused({"ai_paused": False, "paused_until": _o(2)}))

    def test_po_case_sa_zobudi_sama(self):
        """Bez zásahu, bez klikania — čas prejde a odpisuje ďalej."""
        import asyncio

        assert not asyncio.run(self._paused({"ai_paused": False, "paused_until": _o(-1)}))

    def test_rucna_pauza_plati_dalej(self):
        import asyncio

        assert asyncio.run(self._paused({"ai_paused": True, "paused_until": None}))

    def test_rozbity_datum_neuspava(self):
        """Pri pochybnosti radšej odpovedať než onemieť bez vysvetlenia."""
        import asyncio

        assert not asyncio.run(self._paused({"ai_paused": False, "paused_until": "zajtra"}))

    def test_zobudenie_zhodi_obe_pauzy(self):
        import asyncio

        t = FakeTransport({"ai_paused": True, "paused_until": _o(3)})
        asyncio.run(t.sleep_until(None))
        assert t.patches == [{"paused_until": None, "ai_paused": False}]

    def test_uspatie_zhodi_rucnu_pauzu(self):
        """Dve pauzy naraz by znamenali, že zobudenie ticho nezaberie."""
        import asyncio

        t = FakeTransport({"ai_paused": True, "paused_until": None})
        asyncio.run(t.sleep_until(_o(2)))
        assert t.patches[0]["ai_paused"] is False

    def test_rucna_pauza_zhodi_uspatie(self):
        import asyncio

        t = FakeTransport({"ai_paused": False, "paused_until": _o(5)})
        asyncio.run(t.set_paused(True))
        assert t.patches[0]["paused_until"] is None

    def test_sleeping_until_vrati_len_platne(self):
        import asyncio

        t = FakeTransport({"paused_until": _o(-2)})
        assert asyncio.run(t.sleeping_until()) is None
        t2 = FakeTransport({"paused_until": _o(2)})
        assert asyncio.run(t2.sleeping_until()) is not None
