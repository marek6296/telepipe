"""Prepínače notifikácií priamo v control botovi.

Klient, ktorý práve dostal otravnú notifikáciu, ju musí vedieť vypnúť tam, kde
ju dostal — nie sa kvôli tomu prihlasovať do appky. Je to tá istá tabuľka a tie
isté stĺpce ako na stránke.
"""
import asyncio

import pytest
from control_bot import ControlBot
from db import TenantDb


class FakeTransport:
    def __init__(self):
        self.posts = []

    async def _post(self, path, body, upsert=False):
        self.posts.append((path, body, upsert))
        return [body]

    async def _get(self, path, params):
        return []

    async def _patch(self, path, params, body):
        return None


def _db():
    return TenantDb(FakeTransport(), "m-1")


class TestZapis:
    def test_prepne_nastavenie(self):
        db = _db()
        asyncio.run(db.set_control_bot_setting("notify_hot_lead", False))
        path, body, upsert = db._t.posts[0]
        assert body["notify_hot_lead"] is False
        assert body["model_id"] == "m-1"
        assert upsert, "riadok nemusí existovať — modelka mohla vzniknúť pred migráciou"

    def test_poistky_workera_sa_prepisat_nedaju(self):
        """`*_sent_at` nie sú nastavenia. Kto ich prepíše, vypne si ochranu
        proti opakovaným správam a report mu chodí dokola."""
        db = _db()
        for zakazane in (
            "daily_report_sent_at",
            "weekly_report_sent_at",
            "credits_warned_at",
            "model_id",
        ):
            with pytest.raises(ValueError):
                asyncio.run(db.set_control_bot_setting(zakazane, True))
        assert db._t.posts == [], "nič také sa nesmie dostať do databázy"

    def test_vsetky_prepinace_z_menu_su_povolene(self):
        """Menu bota a whitelist databázy sa nesmú rozísť — inak tlačidlo
        vyzerá, že funguje, a v skutočnosti hodí chybu."""
        z_menu = {stlpec for stlpec, _, _ in ControlBot._NOTIFIKACIE}
        assert z_menu <= set(TenantDb.PREPINACE), z_menu - set(TenantDb.PREPINACE)


class TestMenu:
    def test_su_tam_vsetky_notifikacie_ktore_posielame(self):
        """Čo vie bot poslať, to sa musí dať aj vypnúť."""
        import oznamy

        z_udalosti = {stlpec for stlpec, _, _ in oznamy.UDALOSTI.values()}
        v_menu = {stlpec for stlpec, _, _ in ControlBot._NOTIFIKACIE}
        chyba = z_udalosti - v_menu
        assert not chyba, f"v menu sa nedá vypnúť: {chyba}"

    def test_ziadne_duplicity(self):
        stlpce = [stlpec for stlpec, _, _ in ControlBot._NOTIFIKACIE]
        assert len(stlpce) == len(set(stlpce))

    def test_popisy_su_anglicky_bez_html(self):
        """Control bot ide cez Telethon (markdown) a hovorí anglicky."""
        for _, popis, _ in ControlBot._NOTIFIKACIE:
            assert "<" not in popis
            assert popis.strip()
