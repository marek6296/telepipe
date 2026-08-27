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
from datetime import datetime, timezone
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


class TestPrehladChatu:
    """🧠 Context — kto je ten človek, keď prepneš z Auto na Semi.

    V automate si modelka píše sama a majiteľ do toho nevidí. Po prepnutí
    dostane kartu s návrhmi pre človeka, ktorého v živote nevidel. Tento
    prehľad je jediné, z čoho vie vybrať odpoveď inak než naslepo.
    """

    import prehlad as _p

    TERAZ = datetime(2026, 8, 25, 21, 0, tzinfo=timezone.utc)

    USER = {
        "tg_id": 8892541276,
        "first_name": "Jose",
        "partner_name": "Jose",
        "username": "josee",
        "msg_count": 39,
        "funnel_stage": "link_sent",
        "paid": True,
        "created_at": "2026-08-24T08:45:00+00:00",
        "summary": "Flirtuje, pýta si fotky, hovoril o práci v stavebníctve.",
    }
    FAKTY = [
        {"key": "work", "value": "construction"},
        {"key": "city", "value": "Madrid"},
    ]
    SPRAVY = [
        {"role": "user", "content": "hey baby"},
        {"role": "assistant", "content": "hey you 😊"},
    ]

    def test_povie_kto_to_je(self):
        out = self._p.telegram(self.USER, self.FAKTY, self.SPRAVY, teraz=self.TERAZ)
        assert "Jose" in out and "@josee" in out

    def test_povie_ako_dlho_a_kolko_sprav(self):
        out = self._p.telegram(self.USER, self.FAKTY, self.SPRAVY, teraz=self.TERAZ)
        assert "39 messages" in out
        assert "talking for" in out

    def test_platiaci_je_vidiet_hned(self):
        out = self._p.telegram(self.USER, [], [], teraz=self.TERAZ)
        assert "has paid" in out

    def test_kto_len_klikol_je_iny_stav(self):
        user = {**self.USER, "paid": False, "link_clicked_at": "2026-08-25T07:19:00+00:00"}
        out = self._p.telegram(user, [], [], teraz=self.TERAZ)
        assert "opened the link" in out
        assert "has paid" not in out

    def test_rozlucka_sa_musi_povedat(self):
        """Odpoveď človeku, s ktorým sa už rozlúčila, je iná — a bez tohto
        riadku by o tom majiteľ nevedel a napísal by mu ako do živého chatu."""
        out = self._p.telegram({**self.USER, "farewell_at": "2026-08-20T00:00:00+00:00"}, [], [])
        assert "said goodbye" in out

    def test_fakty_su_v_prehlade(self):
        out = self._p.telegram(self.USER, self.FAKTY, [], teraz=self.TERAZ)
        assert "work: construction" in out and "city: Madrid" in out

    def test_posledne_spravy_su_oznacene_kto_je_kto(self):
        out = self._p.telegram(self.USER, [], self.SPRAVY, teraz=self.TERAZ)
        assert "him:" in out and "her:" in out

    def test_ukazuje_len_poslednych_par(self):
        vela = [{"role": "user", "content": f"sprava {i}"} for i in range(40)]
        out = self._p.telegram(self.USER, [], vela, teraz=self.TERAZ)
        assert "sprava 39" in out
        assert "sprava 0" not in out

    def test_prazdny_chat_nespadne(self):
        out = self._p.telegram({"tg_id": 1}, [], [], teraz=self.TERAZ)
        assert out.startswith("🧠")

    def test_zmesti_sa_do_telegram_spravy(self):
        """Telegram odmietne správu nad 4096 znakov — vtedy by prehľad neprišiel
        vôbec."""
        dlhe = [{"role": "user", "content": "x" * 300} for _ in range(40)]
        fakty = [{"key": f"k{i}", "value": "y" * 200} for i in range(40)]
        out = self._p.telegram(
            {**self.USER, "summary": "z" * 2000}, fakty, dlhe, teraz=self.TERAZ
        )
        assert len(out) <= 4096

    def test_cudzi_text_nerozbije_formatovanie(self):
        """Dvojica `*` vo fanúšikovej správe by z kusu prehľadu spravila tučné
        písmo, backtick blok kódu — na obrazovke, ktorá má odpovedať na „kto to
        je"."""
        spravy = [{"role": "user", "content": "toto *je* `divne`"}]
        out = self._p.telegram(self.USER, [], spravy, teraz=self.TERAZ)
        telo = out.split("*Last messages*")[1]
        assert "*je*" not in telo and "`divne`" not in telo
        assert "toto je divne" in telo

    def test_podciarknik_v_prezyvke_ostava(self):
        """`simona_here` bez podčiarkovníka je iná prezývka. Osamotená značka
        je v Telethone obyčajný znak, takže sa neodstraňuje."""
        spravy = [{"role": "user", "content": "napis mi na simona_here"}]
        out = self._p.telegram(self.USER, [], spravy, teraz=self.TERAZ)
        assert "simona_here" in out

    def test_meno_z_telegramu_ma_prednost_pred_prezyvkou(self):
        """`partner_name` vyťahuje z rozhovoru model a mýli sa: naostro z vety
        „Definitely" spravil meno. Skutočné meno je fakt, prezývka je doplnok —
        a keď sa líšia, majiteľ hneď vidí, že sa má čo opraviť."""
        user = {**self.USER, "first_name": "Jose", "partner_name": "Definitely"}
        out = self._p.telegram(user, [], [], teraz=self.TERAZ)
        assert out.startswith("🧠 *Jose")
        assert "calls him *Definitely*" in out

    def test_ked_su_meno_a_prezyvka_rovnake_neopakuje_sa(self):
        user = {**self.USER, "first_name": "Jose", "partner_name": "jose"}
        out = self._p.telegram(user, [], [], teraz=self.TERAZ)
        assert "calls him" not in out

    def test_kluc_faktu_je_citatelny(self):
        out = self._p.telegram(self.USER, [{"key": "how_found", "value": "apka"}], [])
        assert "how found: apka" in out


class TestPrehladFanvue:
    import prehlad as _p

    ROW = {
        "display_name": "Living Earthworm",
        "handle": "living-earthworm-713",
        "msg_count": 4,
        "spent_cents": 3099,
        "bought_count": 3,
        "first_seen": "2026-08-25T07:22:00+00:00",
        "wants": "sex chat",
        "summary": "Práve si predplatil, hneď kúpil dva balíčky.",
    }

    def test_ukaze_kolko_minul(self):
        out = self._p.fanvue(self.ROW, [])
        assert "$30.99" in out and "3×" in out

    def test_kto_este_nic_nekupil(self):
        out = self._p.fanvue({**self.ROW, "spent_cents": 0, "bought_count": 0}, [])
        assert "nothing bought yet" in out

    def test_spojenie_s_telegramom_je_najdolezitejsie(self):
        """Kvôli tomuto riadku to celé vzniklo: nie je to cudzí človek."""
        out = self._p.fanvue(self.ROW, [], tg={"user": {"first_name": "Jose"}})
        assert "Same person as" in out and "Jose" in out

    def test_bez_spojenia_sa_nic_netvrdi(self):
        out = self._p.fanvue(self.ROW, [])
        assert "Same person" not in out

    def test_nesplneny_slub_je_varovanie(self):
        out = self._p.fanvue({**self.ROW, "promised_at": "x", "promised_what": "a photo"}, [])
        assert "promised him a photo" in out

    def test_neodomknuta_ponuka_je_varovanie(self):
        out = self._p.fanvue({**self.ROW, "pending_offer_at": "x"}, [])
        assert "offer waiting" in out

    def test_fakty_z_telegramu_sa_pridaju(self):
        out = self._p.fanvue(
            self.ROW, [], tg={"user": {"first_name": "Jose"}, "facts": [{"key": "city", "value": "Madrid"}]}
        )
        assert "city: Madrid" in out


class TestKontextMajuObaKanaly:
    def test_oba_agenty_vedia_zhrnut_chat(self):
        import fanvue_agent
        import userbot

        for trieda in (fanvue_agent.FanvueAgent, userbot.UserBot):
            assert hasattr(trieda, "context_card"), trieda.__name__

    def test_tlacidlo_je_zaregistrovane(self):
        """Bez `ai` v `_APPROVAL_HEADS` by klik ticho nespravil nič."""
        import control_bot

        assert "ai" in control_bot.ControlBot._APPROVAL_HEADS  # noqa: SLF001


class TestUctovanieNavrhov:
    """Každá meraná metóda musí mať svoj druh spotreby.

    NAOSTRO: `suggest` sa pridalo do `MeteredLlm`, ale nie do `KIND_BY_METHOD`.
    `_bill_inner` sa doň pozerá priamo, takže každý návrh v poloautomate hodil
    `KeyError: 'suggest'` a spotreba sa nezapísala vôbec. Volanie to prežilo
    (účtovanie je best-effort), takže sa to prejavilo len v logu.
    """

    def test_kazda_meraná_metoda_ma_druh(self):
        import re

        import credits

        zdroj = __import__("inspect").getsource(credits.MeteredLlm)
        meraná = set(re.findall(r'self\._metered\("([a-z_]+)"', zdroj))
        assert meraná, "regex prestal sedieť — test by inak prešiel naprázdno"
        chyba = meraná - set(credits.KIND_BY_METHOD)
        assert not chyba, f"chýba druh spotreby pre: {sorted(chyba)}"

    def test_navrhy_sa_uctuju_ako_chat(self):
        import credits

        assert credits.KIND_BY_METHOD.get("suggest") == "chat"


class TestVysledokJeVidiet:
    """Napísané zadanie musí ukázať výsledok DOLE, nie prepísať kartu hore.

    Karta býva nad polovicou chatu a často pripnutá. Keď sa prepísala len ona,
    z pohľadu majiteľa sa po „Writing it in her style…" nestalo nič — presne
    takto to vyzeralo dvakrát po sebe.
    """

    def test_napisane_zadanie_posiela_novu_spravu(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")
        i = src.index('elif kind == "semi_brief":')
        telo = src[i : i + 500]
        assert "nova_sprava=True" in telo

    def test_tlacidlo_prepisuje_kartu_na_mieste(self):
        """Pri kliknutí je majiteľ pri karte — nová správa by len zaplnila chat."""
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")
        i = src.index('elif head == "ar":')
        telo = src[i : i + 400]
        assert "nova_sprava" not in telo

    def test_karta_si_so_sebou_berie_vsetko(self):
        """Bez presunu `pid`, kontextu a pripnutia by klik na novú kartu
        hlásil, že už nie je aktuálna."""
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")
        i = src.index("if nova_sprava:")
        telo = src[i : i + 1200]
        for kus in ("mark_pending", "self._cards[novy]", "_zapamataj_chat", "_pin_card"):
            assert kus in telo, kus
