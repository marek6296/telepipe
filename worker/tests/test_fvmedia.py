"""Fotky na Fanvue — výber, ceny a to, že sa nič neposiela dvakrát."""
from __future__ import annotations

import fvmedia


def m(uuid, spicy=False, caption="", fits="", sent=0, active=True, folder="f", price=0):
    return {
        "media_uuid": uuid, "spicy": spicy, "caption": caption, "fits": fits,
        "sent_count": sent, "active": active, "folder": folder, "price_cents": price,
    }


class TestUlohaPriecinka:
    FOLDERS = [{"name": "sfw fotky", "role": "sfw"}, {"name": "platene", "role": "nsfw"}]

    def test_pozna_ulohu(self):
        assert fvmedia.role_of("sfw fotky", self.FOLDERS) == "sfw"
        assert fvmedia.role_of("platene", self.FOLDERS) == "nsfw"

    def test_neznamy_priecinok_sa_nepouzije(self):
        assert fvmedia.role_of("dako ine", self.FOLDERS) == "ignore"

    def test_nezmyselna_uloha_sa_nepouzije(self):
        assert fvmedia.role_of("x", [{"name": "x", "role": "hlúposť"}]) == "ignore"


class TestVyber:
    def test_vyberie_volnu(self):
        out = fvmedia.pick([m("a")], already_sent=set(), spicy=False)
        assert out["media_uuid"] == "a"

    def test_uz_poslanu_nikdy_znova(self):
        """Dvakrát tá istá fotka je najlacnejší spôsob, ako sa prezradiť."""
        assert fvmedia.pick([m("a")], already_sent={"a"}, spicy=False) is None

    def test_nesprávna_ostrost_sa_nepouzije(self):
        assert fvmedia.pick([m("a", spicy=True)], set(), spicy=False) is None
        assert fvmedia.pick([m("a", spicy=False)], set(), spicy=True) is None

    def test_vypnuta_fotka_sa_nepouzije(self):
        assert fvmedia.pick([m("a", active=False)], set(), spicy=False) is None

    def test_uprednostni_tu_co_sedi_na_rec(self):
        media = [m("a", caption="selfie v aute"), m("b", caption="fotka z fitka")]
        out = fvmedia.pick(media, set(), spicy=False, hint="ukaz mi nieco z fitka")
        assert out["media_uuid"] == "b"

    def test_bez_zhody_berie_najmenej_pouzitu(self):
        media = [m("a", sent=5), m("b", sent=1)]
        out = fvmedia.pick(media, set(), spicy=False)
        assert out["media_uuid"] == "b"

    def test_prazdna_zbierka(self):
        assert fvmedia.pick([], set(), spicy=False) is None


class TestCena:
    def test_kazda_fotka_ma_vlastnu_cenu(self):
        """Jedna cena na priečinok by predávala najlepšiu fotku za to isté
        ako najslabšiu."""
        assert fvmedia.price_for(m("a", price=2500)) == 2500
        assert fvmedia.price_for(m("b", price=700)) == 700

    def test_bez_ceny_nula(self):
        assert fvmedia.price_for(m("a")) == 0


class TestPlatenaNesmieOdistZadarmo:
    def test_bez_ceny_sa_neposle(self):
        """Fotka z plateného priečinka bez ceny je presne ten obsah,
        ktorý zadarmo odísť nesmie."""
        assert fvmedia.pick([m("a", spicy=True)], set(), spicy=True, paid=True) is None

    def test_s_cenou_prejde(self):
        out = fvmedia.pick([m("a", spicy=True, price=1500)], set(), spicy=True, paid=True)
        assert out["media_uuid"] == "a"

    def test_vyberie_len_tie_s_cenou(self):
        media = [m("a", spicy=True), m("b", spicy=True, price=900)]
        out = fvmedia.pick(media, set(), spicy=True, paid=True)
        assert out["media_uuid"] == "b"

    def test_zadarmo_cenu_nepotrebuje(self):
        out = fvmedia.pick([m("a")], set(), spicy=False, paid=False)
        assert out["media_uuid"] == "a"


class TestFeed:
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    NOW = _dt(2026, 8, 17, 12, 0, tzinfo=_tz.utc)

    def test_vypnute_znamena_nikdy(self):
        assert fvmedia.due_to_post({"posting_enabled": False, "post_every_h": 1}, self.NOW) is False

    def test_nulovy_odstup_znamena_nikdy(self):
        assert fvmedia.due_to_post({"posting_enabled": True, "post_every_h": 0}, self.NOW) is False

    def test_prvy_raz_ide_hned(self):
        assert fvmedia.due_to_post({"posting_enabled": True, "post_every_h": 24}, self.NOW) is True

    def test_prilis_skoro_nie(self):
        s = {
            "posting_enabled": True, "post_every_h": 24,
            "last_post_at": (self.NOW - self._td(hours=3)).isoformat(),
        }
        assert fvmedia.due_to_post(s, self.NOW) is False

    def test_po_odstupe_ano(self):
        s = {
            "posting_enabled": True, "post_every_h": 24,
            "last_post_at": (self.NOW - self._td(hours=25)).isoformat(),
        }
        assert fvmedia.due_to_post(s, self.NOW) is True

    def test_vyberie_nepouzitu(self):
        media = [m("b"), m("a")]
        assert fvmedia.next_post(media)["media_uuid"] == "a"

    def test_uz_zverejnenu_nikdy_znova(self):
        """Príspevok na feede ostáva navždy a vidia ho všetci naraz."""
        foto = m("a")
        foto["posted_at"] = "2026-08-01T00:00:00+00:00"
        assert fvmedia.next_post([foto]) is None

    def test_zvuk_na_feed_nejde(self):
        zvuk = m("a")
        zvuk["kind"] = "audio"
        assert fvmedia.next_post([zvuk]) is None

    def test_vypnutu_fotku_nezverejni(self):
        assert fvmedia.next_post([m("a", active=False)]) is None

    def test_prazdny_priecinok(self):
        assert fvmedia.next_post([]) is None


class TestPrevod:
    def test_prevezme_popis_od_fanvue(self):
        """Fanvue si obrázky popisuje samo — netreba na to vlastný model."""
        out = fvmedia.flatten(
            {
                "uuid": "u-1",
                "mediaType": "IMAGE",
                "description": "A woman taking a selfie in a bathroom",
                "recommendedPrice": 1200,
            },
            "sfw",
        )
        assert out["media_uuid"] == "u-1"
        assert out["kind"] == "image"
        assert out["caption"].startswith("A woman taking a selfie")
        assert out["price_cents"] == 1200
        assert out["folder"] == "sfw"

    def test_adresy_sa_neukladaju(self):
        """Podpísané URL expirujú — uchováva sa id, nie odkaz."""
        out = fvmedia.flatten(
            {"uuid": "u-1", "mediaType": "image", "variants": [{"url": "https://x/t.jpg"}]},
            "sfw",
        )
        assert "thumb_url" not in out
        assert not any("http" in str(v) for v in out.values())

    def test_zvuk_sa_pozna(self):
        out = fvmedia.flatten({"uuid": "u-2", "mediaType": "audio"}, "x")
        assert out["kind"] == "audio"

    def test_bez_popisu_nepadne(self):
        out = fvmedia.flatten({"uuid": "u-3", "mediaType": "image"}, "x")
        assert out["caption"] == ""
        assert out["price_cents"] == 0

    def test_bez_uuid_sa_zahodi(self):
        assert fvmedia.flatten({"mediaType": "image"}, "x") is None


class TestZvukSaNeposiela:
    def test_zvuk_z_vaultu_sa_nikdy_nevyberie(self):
        """Vo vaulte sedia aj hlasovky. Poslať zvuk ako fotku by bolo trápne."""
        zvuk = m("a")
        zvuk["kind"] = "audio"
        assert fvmedia.pick([zvuk], set(), spicy=False) is None

    def test_obrazok_prejde(self):
        foto = m("a")
        foto["kind"] = "image"
        assert fvmedia.pick([foto], set(), spicy=False)["media_uuid"] == "a"

    def test_chybajuci_typ_sa_berie_ako_obrazok(self):
        assert fvmedia.pick([m("a")], set(), spicy=False)["media_uuid"] == "a"
