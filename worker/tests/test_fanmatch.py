"""Rozpoznanie človeka na Fanvue, keď neprišiel cez checkout odkaz.

Najdôležitejšie testy sú tie, kde sa spojiť NEMÁ. Zle spojený človek je
horší než nespojený — Simona by mu začala pripomínať cudzie zážitky.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fanmatch

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def chat(tg_id, first_name="", username="", days_ago=None, stage="warm"):
    row = {"tg_id": tg_id, "first_name": first_name, "username": username, "funnel_stage": stage}
    if days_ago is not None:
        row["link_sent_at"] = (NOW - timedelta(days=days_ago)).isoformat()
    return row


class TestNormalizacia:
    def test_diakritika_a_velke_pismena(self):
        assert fanmatch.normalise("Jozef Miklóš") == "jozef miklos"

    def test_ozdoby_sa_zahodia(self):
        assert fanmatch.normalise("~*Mike*~ 🔥") == "mike"

    def test_prazdne(self):
        assert fanmatch.normalise(None) == ""


class TestSpojiSa:
    def test_cele_meno_a_cerstvy_odkaz(self):
        fan = {"display_name": "Yogesh", "handle": "yogesh99"}
        out = fanmatch.best(fan, [chat(1, "Yogesh", days_ago=1, stage="link_sent")], NOW)
        assert out and out["tg_id"] == 1

    def test_diakritika_nevadi(self):
        fan = {"display_name": "Tomas"}
        out = fanmatch.best(fan, [chat(1, "Tomáš", days_ago=2, stage="link_sent")], NOW)
        assert out and out["tg_id"] == 1

    def test_prezyvka_sedi_s_username(self):
        fan = {"handle": "bigmike84"}
        out = fanmatch.best(fan, [chat(1, "Michael", "bigmike84", days_ago=5)], NOW)
        assert out and out["tg_id"] == 1

    def test_vysvetlenie_je_zrozumitelne(self):
        fan = {"display_name": "Yogesh"}
        out = fanmatch.best(fan, [chat(1, "Yogesh", days_ago=1, stage="link_sent")], NOW)
        assert "meno sedí celé" in out["why"]


class TestNespojiSa:
    def test_dvaja_rovnaki_johnovia(self):
        """Toto je jadro veci — pri dvoch rovnakých sa hádať nesmie."""
        fan = {"display_name": "John"}
        chats = [chat(1, "John", days_ago=2, stage="link_sent"), chat(2, "John", days_ago=2, stage="link_sent")]
        assert fanmatch.best(fan, chats, NOW) is None

    def test_samotne_krstne_meno_nestaci(self):
        fan = {"display_name": "Mike"}
        assert fanmatch.best(fan, [chat(1, "Mike Smith")], NOW) is None

    def test_odkaz_sam_o_sebe_nestaci(self):
        """Že niekomu odišiel odkaz, ešte neznamená, že prišiel práve on."""
        fan = {"display_name": "Nikto Taky"}
        assert fanmatch.best(fan, [chat(1, "Yogesh", days_ago=1, stage="link_sent")], NOW) is None

    def test_stary_odkaz_uz_nevahá(self):
        fan = {"display_name": "Mike"}
        assert fanmatch.best(fan, [chat(1, "Mike", days_ago=200)], NOW) is None

    def test_uz_obsadeny_clovek_sa_neponuka(self):
        fan = {"display_name": "Yogesh"}
        chats = [chat(1, "Yogesh", days_ago=1, stage="link_sent")]
        assert fanmatch.best(fan, chats, NOW, taken={1}) is None

    def test_ziadne_konverzacie(self):
        assert fanmatch.best({"display_name": "Mike"}, [], NOW) is None

    def test_fanusik_bez_mena(self):
        assert fanmatch.best({}, [chat(1, "Mike", days_ago=1)], NOW) is None


class TestJasnyVitaz:
    def test_lepsi_kandidat_vyhra_ked_je_dost_napred(self):
        fan = {"display_name": "Yogesh", "handle": "yogesh99"}
        chats = [
            chat(1, "Yogesh", days_ago=1, stage="link_sent"),  # celé meno + čerstvý odkaz
            chat(2, "Yogi"),                                    # nič
        ]
        out = fanmatch.best(fan, chats, NOW)
        assert out and out["tg_id"] == 1
