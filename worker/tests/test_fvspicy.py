"""Ostrosť je vlastnosť FOTKY, nie priečinka.

Predloha (`/Users/marek/telegram`) rozhodovala o ostrosti výhradne podľa
priečinka a `_pick_photo` navyše celému výberu prepísala `item["spicy"]` —
takže checkbox „Explicit" v dashboarde nemenil vôbec nič. Priečinok je pritom
len hrubé triedenie a výnimka je vždy: jedna odvážnejšia fotka v „daily" sa
nesmie poslať zadarmo a jedna nevinná v „premium" nemá dôvod predávať sa.

Tri stavy, o ktoré tu ide:
  * `spicy_override is None` — nikto nerozhodol → platí rola priečinka,
  * `True` / `False` — výslovné rozhodnutie majiteľa, ktoré priečinok prebíja.
"""
from __future__ import annotations

import fvmedia
import pytest
from fanvue_agent import FanvueAgent


# ---------------------------------------------------------------------------
# Samotné pravidlo
# ---------------------------------------------------------------------------


class TestEfektivnaOstrost:
    def test_bez_rozhodnutia_plati_priecinok(self):
        assert fvmedia.effective_spicy({}, "nsfw") is True
        assert fvmedia.effective_spicy({}, "sfw") is False

    def test_vyslovne_ano_prebije_sfw_priecinok(self):
        assert fvmedia.effective_spicy({"spicy_override": True}, "sfw") is True

    def test_vyslovne_nie_prebije_nsfw_priecinok(self):
        assert fvmedia.effective_spicy({"spicy_override": False}, "nsfw") is False

    def test_null_nie_je_false(self):
        """Celý dôvod samostatného stĺpca: `spicy` je `not null default false`,
        takže „nikto nerozhodol" a „nie je ostrá" by v ňom vyzerali rovnako."""
        assert fvmedia.effective_spicy({"spicy_override": None}, "nsfw") is True

    def test_neznama_rola_je_bezpecna(self):
        assert fvmedia.effective_spicy({}, "ignore") is False
        assert fvmedia.effective_spicy({}, "") is False


# ---------------------------------------------------------------------------
# Výber fotky v agentovi
# ---------------------------------------------------------------------------


class _Db:
    """Vault dvoch priečinkov. `media` je zoznam riadkov `fv_media`."""

    def __init__(self, media, folders=None):
        self._media = media
        self._folders = folders or [
            {"name": "daily", "role": "sfw"},
            {"name": "premium", "role": "nsfw"},
        ]

    async def folders(self):
        return list(self._folders)

    async def media_in(self, folder):
        # Kópie, nech si test nevšimne prepis až cez zdieľaný slovník.
        return [dict(m) for m in self._media if m["folder"] == folder]

    async def sent_media(self, fan_uuid):
        return set()


def _foto(uuid, folder, *, override=None, price=0, caption=""):
    row = {
        "media_uuid": uuid,
        "folder": folder,
        "kind": "image",
        "caption": caption,
        "price_cents": price,
        "active": True,
        "sent_count": 0,
    }
    if override is not None:
        row["spicy_override"] = override
    return row


SETTINGS = {"send_photos": True, "free_photo_max": 5}
FAN = {"uuid": "fan-1", "text": "send me a pic"}


async def _vyber(media, *, moment="", foto_ok=True, dlzi=False, folders=None):
    agent = FanvueAgent(_Db(media, folders), api=None, llm=None)
    return await agent._pick_photo(
        FAN, {}, SETTINGS, moment=moment, foto_ok=foto_ok, kde="home", dlzi=dlzi
    )


class TestVyberFotky:
    async def test_ostra_fotka_v_sfw_priecinku_neodide_zadarmo(self):
        """Toto je celý dôvod tejto zmeny: doteraz by odišla ako bežná fotka,
        lebo o ostrosti rozhodoval priečinok a fotku sa nikto nepýtal."""
        media = [
            _foto("ostra", "daily", override=True),
            _foto("bezna", "daily"),
        ]
        vybrana = await _vyber(media)
        assert vybrana is not None
        assert vybrana["media_uuid"] == "bezna"

    async def test_ked_je_v_sfw_priecinku_len_ostra_neposle_sa_nic(self):
        media = [_foto("ostra", "daily", override=True)]
        assert await _vyber(media) is None

    async def test_bezpecna_fotka_v_nsfw_priecinku_smie_ist_zadarmo(self):
        """Majiteľ o nej výslovne povedal, že ostrá nie je — priečinok ju už
        neprebíja. Cena sa pri bezplatnej fotke aj tak nuluje."""
        media = [_foto("nevinna", "premium", override=False, price=900)]
        vybrana = await _vyber(media)
        assert vybrana is not None
        assert vybrana["media_uuid"] == "nevinna"
        assert vybrana["price_cents"] == 0

    async def test_bezpecna_fotka_z_nsfw_priecinku_sa_uz_nepredava(self):
        media = [_foto("nevinna", "premium", override=False, price=900)]
        assert await _vyber(media, moment="asked") is None

    async def test_bez_vlastneho_rozhodnutia_plati_priecinok(self):
        """Zvyčajný prípad musí ostať presne ako doteraz."""
        media = [_foto("bezna", "daily"), _foto("platena", "premium", price=900)]
        assert (await _vyber(media))["media_uuid"] == "bezna"
        assert (await _vyber(media, moment="asked"))["media_uuid"] == "platena"

    async def test_ostra_v_sfw_priecinku_bez_ceny_sa_nepreda(self):
        """`pick(paid=True)` ostáva nedotknutá: fotka bez ceny by odišla
        zadarmo a to je presne ten obsah, ktorý zadarmo odísť nesmie."""
        media = [_foto("ostra", "daily", override=True)]
        assert await _vyber(media, moment="asked") is None

    async def test_ostra_v_sfw_priecinku_s_cenou_sa_preda(self):
        media = [_foto("ostra", "daily", override=True, price=1200)]
        vybrana = await _vyber(media, moment="asked")
        assert vybrana is not None and vybrana["price_cents"] == 1200

    async def test_priecinky_ignore_a_post_sa_neberu(self):
        folders = [
            {"name": "archiv", "role": "ignore"},
            {"name": "feed", "role": "post"},
        ]
        media = [_foto("x", "archiv"), _foto("y", "feed")]
        assert await _vyber(media, folders=folders) is None

    async def test_vypnute_posielanie_fotiek_je_nadradene(self):
        agent = FanvueAgent(_Db([_foto("bezna", "daily")]), api=None, llm=None)
        assert await agent._pick_photo(
            FAN, {}, {"send_photos": False}, moment="", foto_ok=True, kde="home", dlzi=False
        ) is None

    async def test_z_fitka_sa_bezna_fotka_neposiela(self):
        """`can_take_photo` ostáva nedotknutá — fotka z fitka prezradí viac
        než akákoľvek veta."""
        agent = FanvueAgent(_Db([_foto("bezna", "daily")]), api=None, llm=None)
        assert await agent._pick_photo(
            FAN, {}, SETTINGS, moment="", foto_ok=True, kde="gym", dlzi=False
        ) is None
