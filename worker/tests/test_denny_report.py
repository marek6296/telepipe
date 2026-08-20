"""Denný súhrn — kedy sa posiela a kedy nie.

Najdrahšia chyba tu nie je zlý text, ale report poslaný tridsaťkrát: sweeper
beží každé tri minúty a bez poistky by v okne po konci hlásil stále dokola.
"""
from datetime import datetime, timedelta, timezone

import denny_report as dr


def _cas(h, m=0):
    return datetime(2026, 8, 20, h, m, tzinfo=timezone.utc)


class TestKedyPoslat:
    # Simonino okno: 12:12 -> 02:30 (732 -> 150)
    START, END = 732, 150

    def test_hned_po_konci_okna_ano(self):
        assert dr.treba_poslat(_cas(2, 35), self.START, self.END, None)

    def test_v_okne_nie(self):
        """Uprostred jej dňa nemá čo zhŕňať — deň ešte beží."""
        assert not dr.treba_poslat(_cas(20, 0), self.START, self.END, None)

    def test_dlho_po_konci_uz_nie(self):
        """Report o ôsmich hodinách neskôr je len otravná notifikácia."""
        assert not dr.treba_poslat(_cas(11, 0), self.START, self.END, None)

    def test_dnes_uz_bol_nie(self):
        pred_hodinou = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert not dr.treba_poslat(_cas(2, 35), self.START, self.END, pred_hodinou)

    def test_vcera_bol_dnes_ano(self):
        vcera = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        assert dr.treba_poslat(_cas(2, 35), self.START, self.END, vcera)

    def test_pokazeny_datum_nezablokuje(self):
        """Radšej report navyše než žiadny kvôli pokazenému poľu."""
        assert dr.treba_poslat(_cas(2, 35), self.START, self.END, "toto nie je dátum")

    def test_nonstop_modelka_dostane_o_polnoci(self):
        """Bez okna niet konca dňa — vtedy je polnoc jediný rozumný bod."""
        assert dr.treba_poslat(_cas(0, 10), 0, 0, None)
        assert not dr.treba_poslat(_cas(13, 0), 0, 0, None)


class TestZostavenie:
    async def test_bez_konverzacii_nic(self):
        class Db:
            async def recent_conversations(self, limit=20):
                return []
        assert await dr.zostav(Db(), None) is None

    async def test_stare_konverzacie_sa_nepocitaju(self):
        """Kto nepísal celý deň, do dnešného súhrnu nepatrí."""
        davno = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

        class Db:
            async def recent_conversations(self, limit=20):
                return [{"tg_id": 1, "first_name": "Old", "last_incoming_at": davno}]
            async def recent_messages(self, tg_id, limit):
                return []
        assert await dr.zostav(Db(), None) is None

    async def test_zlyhanie_llm_nezhodi_report(self):
        teraz = datetime.now(timezone.utc).isoformat()

        class Db:
            async def recent_conversations(self, limit=20):
                return [{"tg_id": 1, "first_name": "Jane", "last_incoming_at": teraz}]
            async def recent_messages(self, tg_id, limit):
                return [{"role": "user", "content": "ahoj"}]

        class Llm:
            async def report(self, system, podklad):
                raise RuntimeError("model spadol")

        assert await dr.zostav(Db(), Llm()) is None

    async def test_podklad_obsahuje_mena_a_pocty(self):
        teraz = datetime.now(timezone.utc).isoformat()
        videne = {}

        class Db:
            async def recent_conversations(self, limit=20):
                return [{"tg_id": 1, "first_name": "Jane", "last_incoming_at": teraz,
                         "funnel_stage": "warm", "created_at": teraz}]
            async def recent_messages(self, tg_id, limit):
                return [{"role": "user", "content": "chyba mi tvoj hlas"}]

        class Llm:
            async def report(self, system, podklad):
                videne["podklad"] = podklad
                return "Jane je nazhavená."

        text = await dr.zostav(Db(), Llm())
        assert text and "Daily summary" in text
        assert "Jane" in videne["podklad"]
        assert "1 nových" in videne["podklad"]
        assert "chyba mi tvoj hlas" in videne["podklad"]
