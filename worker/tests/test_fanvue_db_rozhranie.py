"""Vie `TenantFanvueDb` všetko, čo od nej Fanvue vetva pýta?

PREČO TENTO TEST EXISTUJE
-------------------------
Toto sa naozaj stalo: do `fanvue_agent` pribudlo volanie
`self._db.control_bot_settings()`, `TenantFanvueDb` tú metódu nemala — a celé
kolo Fanvue padalo na `AttributeError` každých päť sekúnd. Vyše dňa sa
neodpisovalo, nesynchronizoval vault a nespracovali sa udalosti. Bežné testy to
nechytili, lebo používajú vlastné fake objekty: tie majú presne tie metódy,
ktoré si test doplní.

Pre telegramovú vetvu takáto poistka existuje (`test_tenant_db.py`), pre Fanvue
chýbala. Toto ju dopĺňa: číta ZDROJOVÝ KÓD a porovnáva volania s tým, čo trieda
naozaj má. Vďaka tomu chytí aj metódu, ktorú niekto pridá zajtra.
"""
import re
from pathlib import Path

import fanvue_tenant

SRC = Path(__file__).resolve().parents[1] / "src"


def _volania(subor: str, prefix: str) -> set:
    """Mená metód volaných na danom objekte v danom súbore."""
    text = (SRC / subor).read_text(encoding="utf-8")
    return set(re.findall(rf"{re.escape(prefix)}\.([a-z_][a-z0-9_]*)\(", text))


def _ma(trieda) -> set:
    return {m for m in dir(trieda) if not m.startswith("__")}


class TestRozhranie:
    def test_agent_nevola_nic_co_db_nema(self):
        chyba = _volania("fanvue_agent.py", "self._db") - _ma(fanvue_tenant.TenantFanvueDb)
        assert not chyba, (
            "fanvue_agent volá metódy, ktoré TenantFanvueDb nemá: "
            f"{sorted(chyba)} — kolo Fanvue by na nich padlo"
        )

    def test_vault_nevola_nic_co_db_nema(self):
        chyba = _volania("fvvault.py", "self._db") - _ma(fanvue_tenant.TenantFanvueDb)
        assert not chyba, f"fvvault volá metódy, ktoré TenantFanvueDb nemá: {sorted(chyba)}"

    def test_tenant_sam_nevola_nic_co_db_nema(self):
        chyba = _volania("fanvue_tenant.py", "self._db") - _ma(fanvue_tenant.TenantFanvueDb)
        assert not chyba, f"fanvue_tenant volá metódy, ktoré TenantFanvueDb nemá: {sorted(chyba)}"

    def test_test_naozaj_nieco_kontroluje(self):
        """Poistka proti tomu, aby test prešiel len preto, že nič nenašiel."""
        volania = _volania("fanvue_agent.py", "self._db")
        assert len(volania) > 15, f"našlo sa len {len(volania)} volaní — regex asi prestal sedieť"
        assert "control_bot_settings" in volania, "práve to volanie, ktoré vetvu zhodilo"


class TestChybajuceMetody:
    """Tri metódy, ktoré chýbali. Menovite, nech je jasné, čo sa opravovalo."""

    def test_control_bot_settings(self):
        assert hasattr(fanvue_tenant.TenantFanvueDb, "control_bot_settings")

    def test_get_user(self):
        assert hasattr(fanvue_tenant.TenantFanvueDb, "get_user")

    def test_update_user(self):
        assert hasattr(fanvue_tenant.TenantFanvueDb, "update_user")


class FakeTransport:
    """Zachytáva, čo by išlo do PostgRESTu."""

    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.gety = []
        self.patche = []

    async def _get(self, path, params):
        self.gety.append((path, dict(params)))
        return list(self.rows)

    async def _patch(self, path, params, body):
        self.patche.append((path, dict(params), dict(body)))


def _db(rows=None):
    db = fanvue_tenant.TenantFanvueDb.__new__(fanvue_tenant.TenantFanvueDb)
    db._t = FakeTransport(rows)
    db.model_id = "m-1"
    return db


class TestNoveMetody:
    """Cudzia modelka je cudzia — každý dotaz musí byť viazaný na `model_id`.

    Trieda deleguje `_get`/`_patch` na transport, takže stačí podstrčiť
    transport. Nič sa neprepisuje na triede: prepísaná trieda by ostala
    prepísaná aj pre testy, ktoré bežia po tomto súbore.
    """

    def test_get_user_je_viazany_na_model_aj_cloveka(self):
        import asyncio

        db = _db([{"tg_id": 42, "first_name": "Ruto"}])
        out = asyncio.run(db.get_user(42))
        assert out["first_name"] == "Ruto"
        path, params = db._t.gety[0]
        assert path == "/dm_users"
        assert params["model_id"] == db._mine
        assert params["tg_id"] == "eq.42"

    def test_get_user_bez_riadku_vrati_none(self):
        import asyncio

        assert asyncio.run(_db([]).get_user(42)) is None

    def test_update_user_nesiahne_na_cudziu_modelku(self):
        import asyncio

        db = _db()
        asyncio.run(db.update_user(42, {"paid": True}))
        path, params, body = db._t.patche[0]
        assert path == "/dm_users"
        assert params["model_id"] == db._mine, "bez toho by patch trafil aj cudzí riadok"
        assert params["tg_id"] == "eq.42"
        assert body == {"paid": True}

    def test_nastavenia_bota_su_viazane_na_model(self):
        import asyncio

        db = _db([{"notify_hot_lead": False}])
        out = asyncio.run(db.control_bot_settings())
        assert out == {"notify_hot_lead": False}
        assert db._t.gety[0][1]["model_id"] == db._mine

    def test_chybajuci_riadok_nastaveni_nie_je_chyba(self):
        """Modelka mohla vzniknúť pred migráciou — vtedy platia defaulty."""
        import asyncio

        assert asyncio.run(_db([]).control_bot_settings()) == {}

    def test_pad_databazy_neprerusi_notifikacie(self):
        import asyncio

        db = _db()

        async def rozbite(path, params):
            raise RuntimeError("databáza je preč")

        db._t._get = rozbite
        assert asyncio.run(db.control_bot_settings()) == {}
