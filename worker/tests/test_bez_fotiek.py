"""Nesľubuj, čo nemáš — modelka bez fotiek nesmie fotku ponúkať.

ODKIAĽ TO PRIŠLO. Simona nemá v albume ani jednu fotku (`photos_enabled=false`,
0 riadkov v `photos`), a napriek tomu naostro napísala:

    „at the gym right now between sets 💪 maybe i send u one later if u earn it"
    „maybe that pic of ur queen when u wake tho 😜"
    „cooking right now actually just simple pasta … maybe a quick snap later"

Trom rôznym ľuďom, a nikdy nič neprišlo. Príčina bola v tom, že prompt
o fotkách MLČAL: sekcia sa skladala len vtedy, keď fotka naozaj išla alebo keď
si ju niekto vypýtal. Keď mlčí prompt, model si domyslí — a domyslí si to, čo
by povedalo dievča, ktoré fotky má.

Nesplnený sľub je pritom to prvé, na čom sa pozná automat.
"""
from __future__ import annotations

from persona import build_system_prompt

PERSONA = {
    "name": "Simona",
    "backstory": "23, LA",
    "msg_style": "krátko",
    "tone": "hravo",
    "cta_link": "https://www.fanvue.com/sima.sima",
}
USER = {"tg_id": 1, "msg_count": 20, "funnel_stage": "warm", "partner_name": "Leon"}


def _prompt(**kw) -> str:
    zaklad = dict(persona=PERSONA, user=USER, allow_link=False, asked_if_ai=False)
    zaklad.update(kw)
    return build_system_prompt(**zaklad)


class TestKedNemaFotky:
    def test_dostane_zakaz_ponukat(self):
        out = _prompt(no_photos=True)
        assert "FOTKY NEPOSIELAŠ VÔBEC" in out

    def test_zakaz_menuje_konkretne_vyhovorky(self):
        """Všeobecné „nesľubuj" model obíde. Toto sú vety, ktoré naozaj písala."""
        out = _prompt(no_photos=True)
        assert "neskôr" in out
        assert "zaslúžiš" in out
        assert "možno" in out

    def test_zakazuje_aj_tvrdenie_ze_prave_fotila(self):
        """„just been shooting some pics today" je sľub v prezlečení."""
        assert "práve som nejaké fotila" in _prompt(no_photos=True)

    def test_nesmie_povedat_ze_fotky_nema(self):
        """Výhovorka je horšia než mlčanie — znie ako porucha, nie ako človek."""
        out = _prompt(no_photos=True)
        assert "nepovedz, že fotky nemáš" in out

    def test_ked_je_odkaz_na_rade_posle_ho(self):
        """Jediná cesta von, ktorá nie je klamstvo: fotky naozaj sú, na stránke."""
        out = _prompt(no_photos=True, allow_link=True)
        assert "fotky máš na svojej stránke" in out

    def test_bez_povoleneho_odkazu_len_odvedie_rec(self):
        """Odkaz pri každej zmienke o fotke by znel ako predajca — a v tomto
        chate ešte nemá čo robiť."""
        out = _prompt(no_photos=True, allow_link=False)
        assert "odveď reč inam" in out
        assert "fotky máš na svojej stránke" not in out

    def test_bez_odkazu_v_persone_neposiela_nikam(self):
        out = build_system_prompt(
            persona={**PERSONA, "cta_link": ""}, user=USER, allow_link=True,
            asked_if_ai=False, no_photos=True,
        )
        assert "odveď reč inam" in out


class TestKedFotkyMa:
    def test_nic_navyse_sa_nepridava(self):
        out = _prompt(no_photos=False)
        assert "FOTKY NEPOSIELAŠ VÔBEC" not in out

    def test_vypytana_fotka_ma_stare_pravidlo(self):
        out = _prompt(no_photos=False, photo_wanted=True)
        assert "FOTKU PÝTA, ALE ŽIADNU NEPOSIELAŠ" in out

    def test_prazdny_album_prebije_vypytanu_fotku(self):
        """Keď si ju vypýta a ona žiadnu nemá, platí prísnejšie pravidlo —
        staré dovoľuje „neskôr", čo je práve ten nesplniteľný sľub."""
        out = _prompt(no_photos=True, photo_wanted=True)
        assert "FOTKY NEPOSIELAŠ VÔBEC" in out
        assert "FOTKU PÝTA, ALE ŽIADNU NEPOSIELAŠ" not in out

    def test_ked_fotka_naozaj_ide_zakaz_neplati(self):
        """Zákaz sa nesmie objaviť v tej istej odpovedi, v ktorej fotka odchádza."""
        out = _prompt(no_photos=True, photo={"caption": "selfie z postele"})
        assert "PRÁVE MU POSIELAŠ FOTKU" in out
        assert "FOTKY NEPOSIELAŠ VÔBEC" not in out


class TestFanvueTrezor:
    """To isté na Fanvue: prázdny trezor sa nesmie predávať."""

    import fvflow as _f

    ROW = {"msg_count": 30, "free_photos": 0}
    NASTAVENIA = {"sell_content": True, "offer_after_msgs": 5, "free_photo_max": 2}

    def test_prazdny_trezor_zakazuje_ponuky(self):
        out = self._f.guidance(self.ROW, self.NASTAVENIA, "nudge", True, False, ma_media=False)
        assert "NEMÁŠ ČO POSLAŤ" in out
        assert "NEPONÚKAJ" in out

    def test_prazdny_trezor_zakazuje_ceny(self):
        """„opíš, čo si nafotila, a povedz cenu" nad prázdnym trezorom je podvod."""
        out = self._f.guidance(self.ROW, self.NASTAVENIA, "asked", False, True, ma_media=False)
        assert "Nehovor ceny" in out
        assert "povedz aj cenu" not in out

    def test_rozhovor_pokracuje_normalne(self):
        """Chýba obsah, nie chuť sa baviť — inak by z nej bol drevený automat."""
        out = self._f.guidance(self.ROW, self.NASTAVENIA, "", False, False, ma_media=False)
        assert "Rozhovor tým nekončí" in out

    def test_s_obsahom_platia_povodne_pravidla(self):
        out = self._f.guidance(self.ROW, self.NASTAVENIA, "asked", False, True, ma_media=True)
        assert "NEMÁŠ ČO POSLAŤ" not in out
        assert "PÝTA SI NIEČO OSTRÉ" in out


class TestObaAgentyToOveruju:
    def test_telegram_aj_fanvue_maju_kontrolu(self):
        import fanvue_agent
        import userbot

        assert hasattr(userbot.UserBot, "_ma_co_poslat")
        assert hasattr(fanvue_agent.FanvueAgent, "_ma_media")

    def test_cache_sa_nepyta_pri_kazdej_sprave(self):
        import fanvue_agent
        import userbot

        assert userbot._FOTKY_TTL_S >= 60
        assert fanvue_agent._MEDIA_TTL_S >= 60

    def test_vypnuty_prepinac_je_odpoved_bez_dotazu(self):
        """Vypnuté posielanie fotiek = nemá čo poslať, a nestojí to dotaz."""
        import asyncio

        import fanvue_agent

        agent = fanvue_agent.FanvueAgent.__new__(fanvue_agent.FanvueAgent)
        agent._media = True
        agent._media_at = float("-inf")
        assert asyncio.run(agent._ma_media({"send_photos": False})) is False
