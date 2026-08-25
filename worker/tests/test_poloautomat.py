"""Poloautomatický režim: tri návrhy, pregenerovanie a zadanie vlastnými slovami.

ODKIAĽ TO PRIŠLO. Karta v control bote ponúkla tri odpovede, ktoré boli
prakticky tá istá veta: „hey 😄 just chillin in bed still awake", „aww thats
sweet 😘 day was long but im good now just lazy in bed", „mmm hey baby 😉 im
good just laying here". Zadanie znelo „iný uhol/nálada (hravá, vrúcna,
dráždivá)" — lenže nálada nie je ťah a model na ňu vráti tri verzie toho
istého s iným emoji.

Tieto testy nekontrolujú, či je odpoveď dobrá — to sa testom nedá. Kontrolujú,
či sa modelu vôbec zadalo to, o čo ide, a či sa zadanie od majiteľa nedostane
do chatu doslova.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import fvflow
import llm as llm_mod
import zadanie


class FakeChat:
    """Zachytí, čo sa poslalo modelu, a vráti pripravenú odpoveď."""

    def __init__(self, odpoved: str) -> None:
        self.odpoved = odpoved
        self.messages: List[Dict[str, str]] = []
        self.system = ""

    async def __call__(self, model, messages, max_tokens, temperature) -> str:
        self.messages = messages
        self.system = messages[0]["content"]
        return self.odpoved


def _llm(odpoved: str) -> tuple:
    client = llm_mod.Llm.__new__(llm_mod.Llm)
    client._model = "test"  # noqa: SLF001
    fake = FakeChat(odpoved)
    client._chat = fake  # noqa: SLF001
    return client, fake


class TestZadanieUhlov:
    ODPOVED = "prva\n~~~\ndruha\n~~~\ntretia"

    def test_uhly_idu_do_promptu(self):
        client, fake = _llm(self.ODPOVED)
        out = asyncio.run(
            client.suggest("PERSONA", [], angles=["choď s ním ďalej", "natiahni to k obsahu", "nechaj hovoriť jeho"])
        )
        assert out == ["prva", "druha", "tretia"]
        assert "choď s ním ďalej" in fake.system
        assert "natiahni to k obsahu" in fake.system

    def test_ziada_rozne_tahy_nie_nalady(self):
        client, fake = _llm(self.ODPOVED)
        asyncio.run(client.suggest("PERSONA", []))
        assert "INÝ ŤAH" in fake.system
        assert "nesmú byť tri verzie tej istej vety" in fake.system

    def test_vsetky_musia_sediet_do_konverzacie(self):
        client, fake = _llm(self.ODPOVED)
        asyncio.run(client.suggest("PERSONA", []))
        assert "hocijakého chatu" in fake.system, "chýba zákaz univerzálnych viet"

    def test_persona_ostava_zakladom(self):
        """Návrhy píše tá istá modelka — prompt sa nenahrádza, len dopĺňa."""
        client, fake = _llm(self.ODPOVED)
        asyncio.run(client.suggest("TOTO JE PERSONA", []))
        assert fake.system.startswith("TOTO JE PERSONA")

    def test_seed_zmeni_zadanie(self):
        """Bez toho by pregenerovanie vrátilo tie isté vety a tlačidlo by
        vyzeralo pokazené."""
        client, prvy = _llm(self.ODPOVED)
        asyncio.run(client.suggest("PERSONA", []))
        bez = prvy.system
        client, druhy = _llm(self.ODPOVED)
        asyncio.run(client.suggest("PERSONA", [], seed="3"))
        assert druhy.system != bez
        assert "NOVÝ POKUS" in druhy.system

    def test_ked_model_marker_nepouzije(self):
        client, _ = _llm("jedna dlha odpoved bez markera")
        assert asyncio.run(client.suggest("P", [])) == ["jedna dlha odpoved bez markera"]


class TestZadanieOdMajitela:
    """„napíš mu, že…" — obsah zadá majiteľ, vetu píše modelka."""

    BRIEF = "podakuj mu ze tu je a opytaj sa ho kto to je"

    def test_prazdne_zadanie_nemeni_nic(self):
        assert zadanie.do_promptu("") == ""
        assert zadanie.do_promptu("   ") == ""

    def test_zadanie_sa_dostane_do_promptu(self):
        out = zadanie.do_promptu(self.BRIEF)
        assert self.BRIEF in out

    def test_zakazuje_doslovny_prepis(self):
        out = zadanie.do_promptu(self.BRIEF)
        assert "NIE text na odoslanie" in out
        assert "neprekladaj" in out

    def test_jazyk_zadania_nie_je_jazyk_odpovede(self):
        """Marek píše po slovensky, chat beží po anglicky. Bez tohto pravidla
        by jedno zadanie prehodilo celý chat do slovenčiny."""
        out = zadanie.do_promptu(self.BRIEF)
        assert "v inom jazyku" in out
        assert "ktorým si s ním píšeš" in out

    def test_pokyny_o_situacii_maju_prednost(self):
        """Zadanie „pošli fotku" nesmie prebiť to, že je práve v posilňovni."""
        assert "drž sa" in zadanie.do_promptu("posli mu fotku")

    def test_dlhe_zadanie_sa_skrati(self):
        out = zadanie.do_promptu("a" * 900)
        assert "a" * 500 in out
        assert "a" * 501 not in out

    def test_viacriadkove_zadanie_ostane_citatelne(self):
        assert "prvy druhy" in zadanie.do_promptu("prvy\n\n  druhy")


class TestTipNadNavrhmi:
    """Kód vie, či sa hodí fotka. Karta to má povedať."""

    def test_nesplneny_slub_je_prvy(self):
        out = fvflow.tip(moment="nudge", photo_ok=True, asked_photo=False, owed=True)
        assert "promised" in out

    def test_ostra_ziadost_je_moment_na_platenu(self):
        out = fvflow.tip(moment="asked", photo_ok=False, asked_photo=False, owed=False)
        assert "paid photo" in out

    def test_neodomknuta_ponuka_zastavi_dalsiu(self):
        out = fvflow.tip(moment="visi", photo_ok=False, asked_photo=False, owed=False)
        assert "don't send another" in out

    def test_pyta_fotku_ale_je_prec(self):
        out = fvflow.tip(moment="", photo_ok=False, asked_photo=True, owed=False, where="gym")
        assert "gym" in out and "promise" in out

    def test_ked_nie_je_co_radit_je_ticho(self):
        """Rada pri každej správe je šum a po treťom raze sa preskakuje."""
        assert fvflow.tip(moment="", photo_ok=False, asked_photo=False, owed=False) == ""

    def test_tipy_su_po_anglicky_ako_cely_control_bot(self):
        vsetky = [
            fvflow.tip("asked", False, False, False),
            fvflow.tip("nudge", False, False, False),
            fvflow.tip("after_buy", False, False, False),
            fvflow.tip("", True, False, False),
        ]
        for text in vsetky:
            assert text, "tip nemá byť prázdny"
            # Slovenské diakritické znaky by prezradili, že sa niekam vlúdila
            # slovenčina do inak anglického control bota.
            assert not set("áäčďéíĺľňóôŕšťúýžÁČĎÉÍĽŇÓŠŤÚÝŽ") & set(text), text


class TestKartaSaSkladaJednotne:
    """Tri cesty, jedna karta — inak sa po návrate z foto-wizardu stratí tip."""

    def test_tip_je_na_karte(self):
        import control_bot

        lines = control_bot._card_lines(  # noqa: SLF001
            "fanvue", "Living Earthworm", "hey", ["a", "b"], hint="📷 photo fits"
        )
        text = "\n".join(lines)
        assert "📷 photo fits" in text
        assert "*1️⃣* a" in text and "*2️⃣* b" in text

    def test_zadanie_je_na_karte_vidiet(self):
        """Aby bolo po pár minútach jasné, prečo tam tie vety sú."""
        import control_bot

        text = "\n".join(
            control_bot._card_lines(  # noqa: SLF001
                "telegram", "Jose", "hey", ["a"], brief="podakuj mu"
            )
        )
        assert "podakuj mu" in text

    def test_bez_tipu_sa_nic_nepridava(self):
        import control_bot

        text = "\n".join(
            control_bot._card_lines("telegram", "Jose", "hey", ["a"])  # noqa: SLF001
        )
        assert "🗒" not in text

    def test_karta_pozna_kanal(self):
        import control_bot

        assert "Fanvue" in control_bot._card_lines("fanvue", "x", "", ["a"])[0]  # noqa: SLF001
        assert "Telegram" in control_bot._card_lines("telegram", "x", "", ["a"])[0]  # noqa: SLF001


class TestObaKanalyViaPregenerovat:
    """Tlačidlo volá `sender.regenerate` — musia ho mať oba kanály."""

    def test_fanvue_aj_telegram_maju_regenerate(self):
        import fanvue_agent
        import userbot

        for trieda in (fanvue_agent.FanvueAgent, userbot.UserBot):
            assert hasattr(trieda, "regenerate"), trieda.__name__

    def test_regenerate_berie_zadanie_aj_seed(self):
        import inspect

        import fanvue_agent
        import userbot

        for trieda in (fanvue_agent.FanvueAgent, userbot.UserBot):
            params = inspect.signature(trieda.regenerate).parameters
            assert "brief" in params, trieda.__name__
            assert "seed" in params, trieda.__name__


class TestPripinanieKariet:
    """Karta čakajúca na rozhodnutie sa pripne a po rozhodnutí odopne.

    ODKIAĽ TO PRIŠLO. V súkromnom chate s botom chodia aj notifikácie, denné
    súhrny a hlásenia o platbách — karta s návrhmi sa v tom po pár hodinách
    stratí a musí sa hľadať. Pripnutá je navrchu.

    Najdôležitejšie je ODOPNUTIE. Karta sa dá vybaviť ôsmimi spôsobmi
    (schválenie, vlastná správa, zadanie, fotka, hlasovka, preskočenie,
    prevzatie, časový fallback) a keby čo i len jeden z nich odopnutie
    vynechal, ostalo by navrchu visieť niečo bez tlačidiel — a miesto pod
    stropom by bolo obsadené navždy.
    """

    def _bot(self, pinned=None):
        import control_bot

        bot = control_bot.ControlBot.__new__(control_bot.ControlBot)
        bot._cards = {}  # noqa: SLF001
        bot._wizard = {}  # noqa: SLF001
        bot._pinned = set(pinned or ())  # noqa: SLF001
        bot._cfg = type("C", (), {"owner_chat_id": 1})()  # noqa: SLF001

        class FakeClient:
            def __init__(self):
                self.pinned = []
                self.unpinned = []

            async def pin_message(self, chat, mid, notify=True):
                self.pinned.append((mid, notify))

            async def unpin_message(self, chat, mid):
                self.unpinned.append(mid)

        bot._client = FakeClient()  # noqa: SLF001
        return bot

    def test_pripne_a_zapamata_si_to(self):
        bot = self._bot()
        asyncio.run(bot._pin_card(55))  # noqa: SLF001
        assert bot._client.pinned == [(55, False)]  # noqa: SLF001
        assert 55 in bot._pinned  # noqa: SLF001

    def test_pripnutie_neposiela_dalsiu_notifikaciu(self):
        """Kartu už poslal bot sám — pripnutie nemá pípnuť druhý raz."""
        bot = self._bot()
        asyncio.run(bot._pin_card(55))  # noqa: SLF001
        assert bot._client.pinned[0][1] is False  # noqa: SLF001

    def test_nad_stropom_sa_uz_nepripina(self):
        import control_bot

        bot = self._bot(pinned=range(control_bot.MAX_PIN))
        asyncio.run(bot._pin_card(999))  # noqa: SLF001
        assert bot._client.pinned == []  # noqa: SLF001
        assert 999 not in bot._pinned  # noqa: SLF001

    def test_strop_je_nizky(self):
        """Pripnuté všetko je to isté ako nepripnuté nič."""
        import control_bot

        assert control_bot.MAX_PIN <= 5

    def test_rozhodnutie_odopne(self):
        bot = self._bot(pinned={55})
        bot._cards[55] = "pid"  # noqa: SLF001
        asyncio.run(bot._forget_card(55))  # noqa: SLF001
        assert bot._client.unpinned == [55]  # noqa: SLF001
        assert 55 not in bot._pinned  # noqa: SLF001
        assert 55 not in bot._cards  # noqa: SLF001

    def test_uvolni_miesto_pre_dalsiu(self):
        import control_bot

        bot = self._bot(pinned=set(range(control_bot.MAX_PIN)))
        asyncio.run(bot._forget_card(0))  # noqa: SLF001
        asyncio.run(bot._pin_card(999))  # noqa: SLF001
        assert 999 in bot._pinned  # noqa: SLF001

    def test_nepripnuta_karta_sa_neodpina(self):
        """Odopínať niečo, čo sme nepripli, by siahalo na cudzie pripnutia."""
        bot = self._bot()
        asyncio.run(bot._forget_card(77))  # noqa: SLF001
        assert bot._client.unpinned == []  # noqa: SLF001

    def test_zlyhanie_pripnutia_nezhodi_kartu(self):
        bot = self._bot()

        async def zly(*a, **kw):
            raise RuntimeError("chat admin required")

        bot._client.pin_message = zly  # noqa: SLF001
        asyncio.run(bot._pin_card(55))  # noqa: SLF001
        assert 55 not in bot._pinned, "neúspešné pripnutie sa nesmie tváriť ako úspešné"  # noqa: SLF001

    def test_zlyhanie_odopnutia_nezhodi_rozhodnutie(self):
        bot = self._bot(pinned={55})

        async def zly(*a, **kw):
            raise RuntimeError("message not found")

        bot._client.unpin_message = zly  # noqa: SLF001
        asyncio.run(bot._forget_card(55))  # noqa: SLF001
        assert 55 not in bot._pinned  # noqa: SLF001

    def test_kazda_cesta_konca_karty_ide_cez_forget(self):
        """Zdrojová poistka: kto vyhodí kartu z `_cards`, musí ju aj odopnúť.

        Preto sa `_cards.pop` smie objaviť LEN vo `_forget_card`. Bez tohto
        testu stačí pri ďalšej novej ceste na to zabudnúť a pripnutá karta bez
        tlačidiel ostane navrchu navždy.
        """
        import re
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")
        popy = [m.start() for m in re.finditer(r"self\._cards\.pop\(", src)]
        zaciatok = src.index("async def _forget_card")
        koniec = src.index("async def _pin_card")
        vonku = [p for p in popy if not (zaciatok < p < koniec)]
        assert not vonku, f"{len(vonku)}× sa karta zabúda mimo `_forget_card`"

    def test_prepinac_existuje_v_menu_aj_v_db(self):
        import control_bot
        import db

        assert "pin_approvals" in db.TenantDb.PREPINACE
        stlpce = [s for s, _, _ in control_bot.ControlBot._NOTIFIKACIE]  # noqa: SLF001
        assert "pin_approvals" in stlpce
