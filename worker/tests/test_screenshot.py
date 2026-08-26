"""Screenshot nie je fotka jeho — a rozdiel treba povedať nahlas.

ČO SA STALO (Simona, 26. 8. 2026). Spýtala sa „howd u find me?", on poslal
snímku JEJ instagramovej story, kde bol odkaz na Telegram. Vision to popísal
vecne — „Man in suit near pier with Ferris wheel, T.me sticker visible" — a
modelka z toho usúdila, že poslal fotku seba:

    ona:  damn u look good in that suit 😘 not some crypto thing lol just chatting
    on:   Which suit, that's your story 😄
    ona:  haha fair the photo kinda did the work for me 😄

Odhalil ju hneď a konverzácia sa už nespamätala („Nah, sounds like a scam to
me"). Popis obrázka bol pritom správny — chýbalo v ňom len to, AKÝ druh
obrázka to je.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import llm as llm_mod


class FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return {"choices": [{"message": {"content": self._content}}]}


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.payload: Dict[str, Any] = {}

    async def post(self, endpoint, json=None, **kw):
        self.payload = json or {}
        return FakeResponse(self.content)


def _vision(content: str):
    client = llm_mod.Llm.__new__(llm_mod.Llm)
    client._vision_model = "test-vision"  # noqa: SLF001
    client._endpoint = "http://test"  # noqa: SLF001
    fake = FakeClient(content)
    client._client = fake  # noqa: SLF001
    client.last_usage = {}
    return client, fake


class TestDruhObrazka:
    def test_screenshot_sa_pozna(self):
        client, _ = _vision("Man in suit near pier, T.me sticker visible\nSCREENSHOT\nNORMAL")
        out = asyncio.run(client.describe_image(b"x"))
        assert out["kind"] == "SCREENSHOT"
        assert "SCREENSHOT" not in out["description"], "značka nepatrí do popisu"
        assert "Man in suit" in out["description"]

    def test_fotka_cloveka_sa_pozna(self):
        client, _ = _vision("Smiling man on a beach\nPERSON\nNORMAL")
        out = asyncio.run(client.describe_image(b"x"))
        assert out["kind"] == "PERSON"

    def test_explicitna_ostava_explicitna(self):
        client, _ = _vision("Close up of genitals\nPERSON\nEXPLICIT")
        out = asyncio.run(client.describe_image(b"x"))
        assert out["explicit"] is True
        assert "EXPLICIT" not in out["description"]

    def test_model_sa_na_druh_naozaj_pyta(self):
        client, fake = _vision("x\nOTHER\nNORMAL")
        asyncio.run(client.describe_image(b"x"))
        text = fake.payload["messages"][0]["content"][0]["text"]
        assert "SCREENSHOT" in text and "PERSON" in text

    def test_stara_odpoved_bez_druhu_nespadne(self):
        """Model môže tretí riadok vynechať — popis musí prísť aj tak."""
        client, _ = _vision("Some photo\nNORMAL")
        out = asyncio.run(client.describe_image(b"x"))
        assert out["description"] == "Some photo"
        assert out["kind"] == ""

    def test_zlyhanie_nezablokuje_odpoved(self):
        client, _ = _vision("x")

        async def zly(*a, **kw):
            raise RuntimeError("vision je dole")

        client._client.post = zly  # noqa: SLF001
        out = asyncio.run(client.describe_image(b"x"))
        assert out["description"] == "" and out["explicit"] is False


class TestHistoriaNesieLenFakt:
    """Do histórie ide fakt, pokyn patrí do promptu.

    Pokyn vlepený do histórie číta model ako súčasť fanúšikovej správy a môže
    sa objaviť v odpovedi. Preto sa značka a pravidlo rozdelili.
    """

    def test_v_historii_je_len_znacka(self):
        import userbot

        assert "SNÍMKU OBRAZOVKY" in userbot.SCREENSHOT_MARKER
        assert "Reaguj" not in userbot.SCREENSHOT_MARKER


class TestPravidloVPrompte:
    """Čo má modelka so snímkou spraviť."""

    def _prompt(self, **kw):
        from behavior import Behavior
        from persona import build_system_prompt

        zaklad = dict(
            persona={"name": "Simona", "backstory": "23, LA", "msg_style": "krátko"},
            user={"tg_id": 1, "msg_count": 4, "funnel_stage": "warm"},
            allow_link=False,
            asked_if_ai=False,
            behavior=Behavior.from_row({}),
        )
        zaklad.update(kw)
        return build_system_prompt(**zaklad)

    def test_bez_snimky_sa_nic_nepridava(self):
        assert "SNÍMKU OBRAZOVKY" not in self._prompt()

    def test_zakazuje_kompliment_na_vyzor(self):
        """Presne to, čo spravila: „damn u look good in that suit"."""
        out = self._prompt(screenshot=True)
        assert "NIE JE TO FOTKA JEHO" in out
        assert "Nechváľ jeho výzor" in out

    def test_nema_snimku_rozoberat(self):
        assert "nerozoberaj" in self._prompt(screenshot=True)

    def test_ma_odbavit_kratko_a_posunut_otazkou(self):
        """Marekovo zadanie: krátke „nice" a otázka, čo tu hľadá."""
        out = self._prompt(screenshot=True)
        assert "nice" in out
        assert "otázkou o ŇOM" in out

    def test_plati_aj_ked_nema_fotky(self):
        """Obe pravidlá sú samostatné — prázdny album snímku neprebije."""
        out = self._prompt(screenshot=True, no_photos=True)
        assert "SNÍMKU OBRAZOVKY" in out
        assert "FOTKY NEPOSIELAŠ VÔBEC" in out

    def test_ked_prave_posiela_fotku_pravidlo_o_snimke_stale_plati(self):
        out = self._prompt(screenshot=True, photo={"caption": "selfie"})
        assert "PRÁVE MU POSIELAŠ FOTKU" in out
        assert "SNÍMKU OBRAZOVKY" in out
