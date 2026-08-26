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


class TestZnackaVHistorii:
    """To, čo sa dostane do histórie, musí modelku varovať."""

    def test_screenshot_ma_varovanie(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "userbot.py").read_text("utf-8")
        assert "nie fotku seba" in src
        assert "Reaguj na to, ČO je na snímke" in src
