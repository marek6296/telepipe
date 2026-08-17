"""Spotreba tokenov sa počíta za CELÉ volanie, nie za posledný pokus.

`Llm._chat` opakuje pokus po 429/5xx a po prázdnom contente (reasoning model
minul budget na myslenie). Poskytovateľ si tokeny z každého pokusu účtuje
rovnako, ale `last_usage` sa doteraz pri každej odpovedi PREPÍSALA — takže do
ledgeru šla len tá posledná a všetko, čo zhorelo cestou, platil Atlas.
"""
from __future__ import annotations

import httpx
import pytest
from llm import Llm, LlmError


def _llm(handler, **kw):
    model = Llm(api_key="k", model="test/model", **kw)
    model._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return model


def _odpoved(text="ahoj", *, vstup=100, vystup=50, status=200, finish="stop"):
    return httpx.Response(
        status,
        json={
            "usage": {"prompt_tokens": vstup, "completion_tokens": vystup},
            "choices": [{"message": {"content": text}, "finish_reason": finish}],
        },
    )


@pytest.fixture
def nespi(monkeypatch):
    """Backoff medzi pokusmi je 2/4/8 s — v teste nie."""
    import asyncio as _asyncio

    async def hned(_s):
        return None

    monkeypatch.setattr(_asyncio, "sleep", hned)


class TestSucetPokusov:
    async def test_dva_neuspesne_pokusy_a_uspech_sa_scitaju(self, nespi):
        stav = {"n": 0}

        def handler(req):
            stav["n"] += 1
            if stav["n"] < 3:
                # 429 s telom — tokeny za prompt už poskytovateľ spotreboval.
                return httpx.Response(
                    429, json={"usage": {"prompt_tokens": 100, "completion_tokens": 10}}
                )
            return _odpoved(vstup=100, vystup=50)

        model = _llm(handler)
        assert await model.reply("sys", []) == "ahoj"
        # 100+100+100 vstup, 10+10+50 výstup — nie len posledný pokus.
        assert model.last_usage == {"input": 300, "output": 70}

    async def test_zdvihnutie_stropu_sa_tiez_ucctuje(self, nespi):
        """Reasoning model minul budget na myslenie a vrátil prázdny text.
        Tie tokeny sú spotrebované a niekto ich zaplatiť musí."""
        stav = {"n": 0}

        def handler(req):
            stav["n"] += 1
            if stav["n"] == 1:
                return _odpoved("", vstup=80, vystup=400, finish="length")
            return _odpoved("konečne", vstup=80, vystup=30)

        model = _llm(handler)
        assert await model.reply("sys", []) == "konečne"
        assert model.last_usage == {"input": 160, "output": 430}

    async def test_uplny_neuspech_nechá_spotrebu_v_last_usage(self, nespi):
        def handler(req):
            return httpx.Response(
                500, json={"usage": {"prompt_tokens": 70, "completion_tokens": 5}}
            )

        model = _llm(handler)
        with pytest.raises(LlmError):
            await model.reply("sys", [])
        # Tri pokusy — volajúci (MeteredLlm) má čo zaúčtovať aj po páde.
        assert model.last_usage == {"input": 210, "output": 15}

    async def test_nove_volanie_zacina_od_nuly(self, nespi):
        def handler(req):
            return _odpoved(vstup=10, vystup=5)

        model = _llm(handler)
        await model.reply("sys", [])
        await model.reply("sys", [])
        assert model.last_usage == {"input": 10, "output": 5}

    async def test_pokazene_usage_nezhodi_volanie(self, nespi):
        def handler(req):
            return httpx.Response(
                200,
                json={
                    "usage": {"prompt_tokens": "nezmysel"},
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                },
            )

        model = _llm(handler)
        assert await model.reply("sys", []) == "ok"
        assert model.last_usage == {"input": 0, "output": 0}


class TestVlastneCesty:
    """`transcribe_voice` a `describe_image` nejdú cez `_chat` — musia sa
    nulovať samy, inak by si niesli súčet z predchádzajúcej odpovede."""

    async def test_prepis_hlasovky_nuluje_predchadzajuce(self, nespi):
        def handler(req):
            return _odpoved("prepis", vstup=20, vystup=8)

        model = _llm(handler)
        await model.reply("sys", [])
        await model.transcribe_voice(b"zvuk")
        assert model.last_usage == {"input": 20, "output": 8}

    async def test_zlyhany_prepis_nenechá_cudziu_spotrebu(self, nespi):
        stav = {"n": 0}

        def handler(req):
            stav["n"] += 1
            if stav["n"] == 1:
                return _odpoved(vstup=999, vystup=999)
            return httpx.Response(500, json={})

        model = _llm(handler)
        await model.reply("sys", [])
        assert await model.transcribe_voice(b"zvuk") == ""
        # Nesmie sa zaúčtovať 999 tokenov z predošlej odpovede.
        assert model.last_usage == {"input": 0, "output": 0}

    async def test_popis_fotky_nuluje_predchadzajuce(self, nespi):
        def handler(req):
            return _odpoved("mačka na parapete\nNORMAL", vstup=30, vystup=12)

        model = _llm(handler)
        await model.reply("sys", [])
        out = await model.describe_image(b"jpeg")
        assert out["explicit"] is False
        assert model.last_usage == {"input": 30, "output": 12}
