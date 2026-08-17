"""Zosúladenie chatu — čo doplniť, kedy mlčať a či kúpil."""
from __future__ import annotations

import fvsync

JA = "creator-1"
ON = "fan-1"


def msg(uuid, sender, text="ahoj", **extra):
    return {"uuid": uuid, "sender": {"uuid": sender}, "text": text, **extra}


class TestKtoNapisal:
    def test_moja_sprava(self):
        assert fvsync.role_of(msg("m1", JA), JA) == "assistant"

    def test_jeho_sprava(self):
        assert fvsync.role_of(msg("m1", ON), JA) == "user"

    def test_bez_odosielatela_je_to_jeho(self):
        assert fvsync.role_of({"uuid": "m1"}, JA) == "user"


class TestText:
    def test_bezny_text(self):
        assert fvsync.as_text(msg("m1", ON, "hey there")) == "hey there"

    def test_hlasovka_sa_pozna(self):
        out = fvsync.as_text(msg("m1", JA, "cuj", hasMedia=True, mediaType="audio"))
        assert out.startswith("(hlasovka)")

    def test_platena_ma_v_pamati_cenu(self):
        out = fvsync.as_text(
            msg("m1", JA, "pre teba", hasMedia=True, mediaType="audio",
                pricing={"USD": {"price": 800}})
        )
        assert "$8.00" in out

    def test_fotka_sa_pozna(self):
        out = fvsync.as_text(msg("m1", JA, "", hasMedia=True, mediaType="image"))
        assert out == "(image)"


class TestCoChyba:
    def test_doplni_len_nezname(self):
        fetched = [msg("m3", ON), msg("m2", JA), msg("m1", ON)]
        out = fvsync.missing({"m1"}, fetched, JA)
        assert [r["message_uuid"] for r in out] == ["m2", "m3"]

    def test_poradie_je_od_najstarsej(self):
        """Fanvue vracia najnovšie prvé — v pamäti musí byť opačne."""
        fetched = [msg("m3", ON), msg("m2", ON), msg("m1", ON)]
        out = fvsync.missing(set(), fetched, JA)
        assert [r["message_uuid"] for r in out] == ["m1", "m2", "m3"]

    def test_role_sa_zachovaju(self):
        out = fvsync.missing(set(), [msg("m2", JA), msg("m1", ON)], JA)
        assert [r["role"] for r in out] == ["user", "assistant"]

    def test_prazdne_spravy_sa_preskocia(self):
        assert fvsync.missing(set(), [msg("m1", ON, "")], JA) == []

    def test_ked_mame_vsetko_nedopln_nic(self):
        assert fvsync.missing({"m1", "m2"}, [msg("m2", JA), msg("m1", ON)], JA) == []


class TestKedyMlcat:
    def test_ked_odpisal_niekto_rucne_mlci(self):
        """Druhá odpoveď by mu do toho písala a mohla by protirečiť."""
        assert fvsync.stay_quiet([msg("m2", JA), msg("m1", ON)], JA) is True

    def test_ked_je_posledna_jeho_odpisuje(self):
        assert fvsync.stay_quiet([msg("m2", ON), msg("m1", JA)], JA) is False

    def test_prazdny_chat_neblokuje(self):
        assert fvsync.stay_quiet([], JA) is False


class TestNakup:
    def test_spocita_kupene(self):
        fetched = [
            msg("m1", JA, purchasedAt="2026-08-01T10:00:00Z"),
            msg("m2", JA, purchasedAt=None),
            msg("m3", JA, purchasedAt="2026-08-05T10:00:00Z"),
        ]
        assert fvsync.bought(fetched) == 2

    def test_najnovsi_nakup(self):
        fetched = [
            msg("m1", JA, purchasedAt="2026-08-01T10:00:00Z"),
            msg("m3", JA, purchasedAt="2026-08-05T10:00:00Z"),
        ]
        assert fvsync.last_bought_at(fetched) == "2026-08-05T10:00:00Z"

    def test_bez_nakupu(self):
        assert fvsync.bought([msg("m1", ON)]) == 0
        assert fvsync.last_bought_at([msg("m1", ON)]) == ""
