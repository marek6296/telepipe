"""Univerzálna ľudská vrstva — platí pre každú modelku, nech si klient nastaví čokoľvek."""
import ludskost
import persona as persona_mod


def _spravy(vzor):
    """`vzor` = reťazec ako 'q.q.' — q = jej správa s otázkou, . = bez nej."""
    rows = []
    for znak in vzor:
        rows.append({"role": "user", "content": "hej"})
        rows.append(
            {"role": "assistant", "content": "co robis?" if znak == "q" else "som doma"}
        )
    return rows


class TestPrednost:
    """Klient si nesmie jedným poľom v persone rozbiť to, čo drží produkt."""

    @staticmethod
    def _prompt(**kw):
        persona = {
            "name": "Lucia", "language": "", "languages": "",
            "lang_primary": "en", "lang_extra": [],
            "backstory": "", "tone": "", "msg_style": "",
            "boundaries": "", "funnel_rules": "", "cta_link": "", "extra_rules": "",
        }
        persona.update(kw)
        return persona_mod.build_system_prompt(
            persona, {"tg_id": 1, "msg_count": 7, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False,
        )

    def test_vrstva_je_v_prompte(self):
        out = self._prompt()
        assert "ČO PLATÍ NADO VŠETKÝM" in out
        assert "KEĎ ŤA SKÚŠA, ČI SI ROBOT" in out

    def test_je_az_za_personou(self):
        """Pravidlo „platí nado všetkým" dáva zmysel len ako posledné."""
        out = self._prompt(msg_style="pis dlhe prepracovane spravy")
        assert out.index("pis dlhe prepracovane spravy") < out.index("ČO PLATÍ NADO VŠETKÝM")

    def test_plati_aj_ked_je_persona_prazdna(self):
        """Nová modelka bez jediného vyplneného poľa má vrstvu tiež."""
        assert "TOTO NEROB NIKDY" in self._prompt()

    def test_pokryva_situacie_ktore_prezradia_ai(self):
        out = self._prompt()
        for co in (
            "VIDEOHOVOR",       # nesľubuje stretnutia
            "SMUTNÉ",           # flirt končí
            "HRUBÝ",            # nepodlieza
            "DRUHÝKRÁT",        # nemení odpovede
            "JEDNO SLOVO",      # nezasype odsekom
            "PENIAZOCH",        # neponúka obsah človeku v núdzi
        ):
            assert co in out, co


class TestFanvueMaToIste:
    def test_vrstva_je_aj_na_fanvue(self):
        """Je to tá istá osoba a tie isté situácie."""
        import fanvue_agent

        out = fanvue_agent.build_prompt(
            {"name": "Lucia", "backstory": "", "tone": "", "msg_style": "",
             "boundaries": "", "extra_rules": "", "examples": "",
             "lang_primary": "en", "lang_extra": []},
            {},
            {"uuid": "u1", "handle": "fan", "display_name": "Fan"},
            {"tg_id": None},
            None,
        )
        assert "KEĎ ŤA SKÚŠA, ČI SI ROBOT" in out


class TestPodielOtazok:
    """Nastavenie je zámer, toto je skutočnosť."""

    def test_prazdna_historia(self):
        assert ludskost.podiel_otazok([]) == 0.0
        assert not ludskost.uz_sa_pytala_dost([])

    def test_dotaznik_sa_potlaci(self):
        rows = _spravy("qqqq")
        assert ludskost.podiel_otazok(rows) == 1.0
        assert ludskost.uz_sa_pytala_dost(rows)

    def test_normalna_konverzacia_nie(self):
        rows = _spravy("q...q...")
        assert ludskost.uz_sa_pytala_dost(rows) is False

    def test_na_zaciatku_sa_nepotlaca(self):
        """Prvé správy sa MAJÚ pýtať — tam sa spoznávajú."""
        assert not ludskost.uz_sa_pytala_dost(_spravy("q"))
        assert not ludskost.uz_sa_pytala_dost(_spravy("qq"))

    def test_pozera_len_na_posledne_spravy(self):
        """Dotazník spred dvoch týždňov nemá brzdiť dnešný rozhovor."""
        rows = _spravy("qqqqqqqq" + "........")
        assert not ludskost.uz_sa_pytala_dost(rows)

    def test_jeho_otazky_sa_neratajú(self):
        rows = [{"role": "user", "content": "co? kde? ako?"} for _ in range(8)]
        assert ludskost.podiel_otazok(rows) == 0.0


class TestPodlahaNaCislach:
    """Nastavenia sú vec vkusu — tieto štyri čísla nie sú.

    Pri nich prestane byť modelka človekom, nech si klient myslí čokoľvek:
    odpoveď do nuly sekúnd, zakaždým rovnako rýchla, s otázkou v každej správe.
    """

    @staticmethod
    def _b(**kw):
        import behavior as bhv

        return bhv.Behavior.from_row({"mode": "real", **kw})

    def test_nulove_cakanie_sa_zdvihne(self):
        b = self._b(read_delay_min_s=0, reply_delay_min_s=0)
        assert b.read_delay_min_s >= 1
        assert b.reply_delay_min_s >= 3

    def test_rovnake_min_a_max_dostane_rozptyl(self):
        """Rovnaké číslo v oboch = rovnaký odstup pri každej správe. Pravidelnosť
        je to prvé, čo si všimne aj človek, aj systém."""
        b = self._b(reply_delay_min_s=10, reply_delay_max_s=10)
        assert b.reply_delay_max_s > b.reply_delay_min_s

    def test_vzdy_okamzita_odpoved_sa_ostrihne(self):
        assert self._b(quick_reply_chance=1.0).quick_reply_chance <= 0.8

    def test_otazky_sa_neostrihavaju_cislom(self):
        """Rieši ich meranie skutočnosti, nie strop na nastavení — strop by z
        „pýtaj sa vždy" spravil náhodu, teda nastavenie klamúce o tom, čo robí."""
        assert self._b(question_chance=1.0).question_chance == 1.0

    def test_rozumne_nastavenie_ostava_nedotknute(self):
        """Podlaha nie je náš názor na to, ako sa má odpisovať."""
        b = self._b(
            read_delay_min_s=5, read_delay_max_s=45,
            reply_delay_min_s=8, reply_delay_max_s=60,
            quick_reply_chance=0.3, question_chance=0.45,
        )
        assert (b.read_delay_min_s, b.read_delay_max_s) == (5, 45)
        assert (b.reply_delay_min_s, b.reply_delay_max_s) == (8, 60)
        assert b.quick_reply_chance == 0.3 and b.question_chance == 0.45

    def test_aj_ked_riadok_chyba(self):
        import behavior as bhv

        b = bhv.Behavior.from_row(None)
        assert b.reply_delay_min_s >= 3


class TestKratkaSprava:
    """Nemá krátke správy — a to je zo všetkých rozdielov ten najväčší.

    Merané 29. 8. na 852 jej správach proti 1176 správam mužov v tých istých
    chatoch (muži sú ľudský základ — sú to skutoční ľudia v tom istom médiu):

                          ona     oni
      medián dĺžky         68      35 znakov
      desiaty percentil    32       7 znakov
      kratšie ako 15 zn.    3 %    21 %

    Marek: „dako divne sa mi zda ze odpisuje, nezda sa ti je to taka divna
    konverzacia a nieje to uplne ako clovek". Toto je z toho merateľná časť.
    """

    def _jej(self, *dlzky):
        return [{"role": "assistant", "content": "x" * d} for d in dlzky]

    def test_ked_su_vsetky_dlhe_ma_byt_kratka(self):
        assert ludskost.ma_byt_kratka(self._jej(40, 50, 60, 70, 45, 55))

    def test_jedna_kratka_v_okne_staci(self):
        """Nevynucuje sa rytmus, len sa bráni tomu, aby krátke chýbali úplne."""
        assert not ludskost.ma_byt_kratka(self._jej(40, 50, 8, 70, 45, 55))

    def test_na_zaciatku_rozhovoru_nie(self):
        """Vynútené „lol" na tretiu vetu v živote vyzerá ako nezáujem."""
        assert not ludskost.ma_byt_kratka(self._jej(40, 50, 60))

    def test_ked_sa_pyta_na_nieco_vazne_nie(self):
        """Na otázku sa tromi slovami odpovedať nedá — bolo by to horšie."""
        assert not ludskost.ma_byt_kratka(
            self._jej(40, 50, 60, 70, 45, 55), caka_odpoved=True
        )

    def test_na_dlhu_spravu_nie(self):
        """Odpovedať „lol" na odsek nie je ľudské, to je odbitie."""
        dlha = " ".join(["slovo"] * 20)
        assert not ludskost.ma_byt_kratka(self._jej(40, 50, 60, 70, 45, 55), dlha)

    def test_pokyn_ziada_najviac_tri_slova(self):
        assert "tri slová" in ludskost.KRATKA_TERAZ


class TestNoveSituacie:
    def test_odbitie_sa_neopakuje_a_nesľubuje(self):
        """Naostro: to isté odbitie dvakrát a on odpísal „ill hold you up to
        that". Sľub s odloženou platnosťou si ľudia pamätajú lepšie než nie."""
        assert "ODBÍJAŠ DRUHÝKRÁT" in ludskost.SITUACIE
        assert "Nič nesľubuj" in ludskost.SITUACIE

    def test_stretnutie_nesmie_znieť_ani_pekne(self):
        """„would be nice to meet one day" je sľub napísaný mäkko."""
        assert "STRETLI" in ludskost.SITUACIE

    def test_nehlasi_co_prave_robi(self):
        assert "NEHLÁS, ČO PRÁVE ROBÍŠ" in ludskost.NIKDY

    def test_nesuhlasi_so_vsetkym(self):
        assert "NEPRIKYVUJ MU NA VŠETKO" in ludskost.NIKDY
