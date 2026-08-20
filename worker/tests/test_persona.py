"""Systémový prompt — jazyková politika modeliek."""
from persona import build_system_prompt


class TestJazyky:
    """Hlavným jazykom s každým — kto napíše jazykom, ktorý vie, dostane odpoveď v ňom.

    Jazyky sú ŠTRUKTÚRA (`lang_primary` + `lang_extra`), nie voľný text. Voľné
    pole `languages` ostáva len ako doplnok vlastnými slovami; samo o sebe už
    modelke jazyk nepridáva — inak by stačilo napísať do textu „vie po nemecky"
    a obišlo by to úroveň aj kontrolu tvaru v databáze.
    """

    @staticmethod
    def _prompt(extra=None, foreign=False, primary="en", note=""):
        persona = {
            "name": "Simona", "language": "", "languages": note,
            "lang_primary": primary, "lang_extra": extra or [],
            "backstory": "", "tone": "", "msg_style": "",
            "boundaries": "", "funnel_rules": "", "cta_link": "", "extra_rules": "",
        }
        return build_system_prompt(
            persona, {"tg_id": 1, "msg_count": 7, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, foreign=foreign,
        )

    def test_zoznam_jazykov_je_v_prompte(self):
        out = self._prompt([{"code": "de", "level": "B1"}])
        assert "JAZYKY, KTORÉ VIEŠ" in out
        assert "German" in out and "úroveň B1" in out

    def test_uroven_meni_pokyn(self):
        """A2 a C1 nesmú dostať ten istý pokyn — inak je úroveň len ozdoba."""
        nizka = self._prompt([{"code": "es", "level": "A2"}])
        vysoka = self._prompt([{"code": "es", "level": "C1"}])
        assert "vieš základy" in nizka
        assert "veľmi dobre" in vysoka
        assert nizka != vysoka

    def test_cudzi_jazyk_smie_odpovedat_v_nom(self):
        out = self._prompt([{"code": "de", "level": "B1"}], foreign=True)
        assert "odpovedz mu V ŇOM" in out

    def test_cudzi_jazyk_nemeni_styl(self):
        """Najčastejší spôsob, ako sa to pokazí: v cudzom jazyku začne písať inak."""
        out = self._prompt([{"code": "de", "level": "B1"}], foreign=True)
        assert "ŠTÝL SA NEMENÍ" in out

    def test_bez_zoznamu_ostava_len_hlavny_jazyk(self):
        """Modelka bez ďalších jazykov sa nesmie zrazu tváriť, že vie po nemecky."""
        out = self._prompt([], foreign=True)
        assert "Vieš iba English" in out
        assert "odpovedz mu V ŇOM" not in out

    def test_pravidlo_plati_AJ_BEZ_detekcie(self):
        """`looks_foreign` chytila v ostrej prevádzke 1 zo 6 španielskych viet.
        Zvyšné prešli bez pravidla a model si ich preložil a odpovedal na obsah."""
        out = self._prompt([], foreign=False)
        assert "KEĎ TI NAPÍŠE JAZYKOM, KTORÝ NEVIEŠ" in out
        assert "NEPREKLADAJ" in out

    def test_nesmie_predavat_na_nezrozumenu_spravu(self):
        """Ayko odpovedala odkazom na Fanvue na „Quisiera besarte"."""
        out = self._prompt([], foreign=False)
        assert "neponúkaj svoju stránku ani odkaz" in out

    def test_ma_konkretne_vety_na_vyhovorenie(self):
        """Bez ukážok model vymyslí jednu frázu a opakuje ju stále dokola."""
        out = self._prompt([], foreign=False)
        assert "what does that mean" in out
        assert "Striedaj to" in out

    def test_zoznam_nema_zvadzat_ku_klamstvu(self):
        out = self._prompt([{"code": "de", "level": "B1"}])
        assert "Nikdy netvrď, že vieš jazyk, ktorý tu nie je" in out

    def test_volny_text_nepridava_jazyk(self):
        """Poznámka je doplnok, nie ďalší jazyk. Inak by obišla úroveň aj CHECK."""
        out = self._prompt([], note="vie aj po grécky")
        assert "vie aj po grécky" in out          # poznámka sa nezahodí
        assert "Iný jazyk NEVIEŠ" in out          # ale zoznam ju za jazyk nepovažuje

    def test_hlavny_jazyk_nie_je_natvrdo_anglictina(self):
        """Jadro pravidiel kedysi hlásilo „ÚROVEŇ ANGLIČTINY" každej modelke."""
        out = self._prompt(primary="de")
        assert "ÚROVEŇ JAZYKA (German)" in out
        assert "ANGLIČTINY" not in out

    def test_s_vedlajsimi_jazykmi_pravidlo_tiez_plati_vzdy(self):
        """Nadpis sa líši podľa toho, či nejaké vedľajšie jazyky má — ale
        pravidlo je v prompte tak či tak, bez ohľadu na detekciu."""
        out = self._prompt([{"code": "en", "level": "B2"}], foreign=False, primary="de")
        assert "KEĎ TI NAPÍŠE INÝM JAZYKOM" in out
        assert "NEPREKLADAJ" in out


class TestUkazkyAStyl:
    """Model sa štýl naučí zo vzorky rádovo lepšie než zo zoznamu zákazov."""

    @staticmethod
    def _prompt(**kw):
        persona = {
            "name": "Simona", "language": "", "languages": "", "backstory": "",
            "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
            "cta_link": "", "extra_rules": "",
        }
        persona.update(kw.pop("persona", {}))
        return build_system_prompt(
            persona, {"tg_id": 1, "msg_count": 7, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, **kw,
        )

    def test_ukazky_z_persony_su_v_prompte(self):
        out = self._prompt(persona={"examples": "on: hey\nty: heyy whats up"})
        assert "TAKTO PÍŠEŠ TY" in out and "heyy whats up" in out

    def test_bez_ukazok_sekcia_nie_je(self):
        assert "TAKTO PÍŠEŠ TY" not in self._prompt()

    def test_jeho_spravy_idu_ako_vzor(self):
        out = self._prompt(his_samples=["wyd rn", "u up"])
        assert "wyd rn" in out and "posledné správy" in out

    def test_zakazane_slova_uz_nie_su_v_prompte(self):
        """Vymenovanie slova ho modelu drží pred očami — rieši to sanitize."""
        out = self._prompt()
        assert "intriguing" not in out and "whilst" not in out


class TestZiadnaDuplicitaOFaktoch:
    """Zhrnutie hovorí o tóne, fakty o faktoch — nesmú sa volať rovnako."""

    def test_zhrnutie_a_fakty_maju_rozne_nadpisy(self):
        out = build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 9, "funnel_stage": "warm",
             "summary": "reaguje dobre na drzost"},
            allow_link=False, asked_if_ai=False,
            fact_sheet="- vodic kamiona",
        )
        assert "AKO VÁM TO SPOLU IDE" in out
        assert "ČO O ŇOM VIEŠ" in out
        assert "ČO O ŇOM VIEŠ Z PREDCHÁDZAJÚCICH SPRÁV" not in out


class TestPozvankaPredava:
    """Samotný odkaz nestačí — musí povedať, čo ho tam čaká."""

    @staticmethod
    def _prompt(allow_link=True, explicit=False, link_sent=False):
        persona = {
            "name": "Simona", "language": "", "languages": "", "backstory": "",
            "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
            "cta_link": "https://www.fanvue.com/sima.sima", "extra_rules": "",
        }
        return build_system_prompt(
            persona, {"tg_id": 1, "msg_count": 12, "funnel_stage": "warm"},
            allow_link=allow_link, asked_if_ai=False, explicit=explicit,
            link_already_sent=link_sent, remind_link=True,
        )

    def test_pri_odkaze_povie_co_ho_caka(self):
        out = self._prompt()
        assert "PREČO tam má ísť" in out and "pikantné" in out

    def test_pri_eskalacii_tiez(self):
        out = self._prompt(allow_link=False, explicit=True)
        assert "čo z toho má" in out

    def test_pripomenutie_tiez_laka(self):
        out = self._prompt(allow_link=False, explicit=True, link_sent=True)
        assert "vypýtať, čo chce" in out

    def test_nikdy_ako_cennik(self):
        assert "nikdy ako cenník" in self._prompt()


class TestNaPrikyvnutieSaNepriostruje:
    @staticmethod
    def _prompt(**kw):
        from persona import build_system_prompt
        return build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 20, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, **kw,
        )

    def test_prikyvnutie_ma_vlastny_pokyn(self):
        out = self._prompt(filler=True)
        assert "LEN PRIKÝVOL" in out
        assert "NEOTVÁRAJ novú tému" in out

    def test_bez_neho_sekcia_nie_je(self):
        assert "LEN PRIKÝVOL" not in self._prompt()


class TestPrvychDvadsatSprav:
    """Prvá fáza je čisté spoznávanie — nudné veci, čo si píšu skutoční ľudia."""

    @staticmethod
    def _prompt(msg_count, **kw):
        from persona import build_system_prompt
        return build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": msg_count, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, **kw,
        )

    def test_na_zaciatku_sa_na_prikyvnutie_spyta(self):
        out = self._prompt(8, filler=True)
        assert "SPÝTAJ SA NIEČO" in out
        assert "na to je ešte skoro" in out

    def test_neskor_uz_len_zareaguje(self):
        out = self._prompt(40, filler=True)
        assert "SPÝTAJ SA NIEČO" not in out
        assert "NEOTVÁRAJ novú tému" in out

    def test_funnel_sa_pred_dvadsiatkou_nezapina(self):
        import funnel

        assert funnel.LEAD_MIN_MESSAGES >= 20
        assert not funnel.should_lead({"msg_count": 15, "created_at": "2020-01-01T00:00:00+00:00"})


class TestHorucaHlasovka:
    def test_ma_vlastny_pokyn(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 40, "funnel_stage": "link_sent"},
            allow_link=False, asked_if_ai=False, hot_voice=True,
        )
        assert "POZRIADNE HORÚCA" in out
        assert "NIKDY nepouži to, čo si už raz povedala" in out


class TestDrzost:
    """Keď je na ňu drzý, prompt jej káže hrdosť, nie asistentské chápanie."""

    def _prompt(self, hostile):
        return build_system_prompt(
            {"name": "Simona", "backstory": "", "tone": "", "msg_style": "",
             "boundaries": "", "funnel_rules": "", "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 7, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, hostile=hostile,
        )

    def test_sekcia_sa_objavi_pri_utoku(self):
        out = self._prompt(True)
        assert "PRÁVE BOL NA TEBA DRZÝ" in out
        assert "roztápaš sa POMALY" in out

    def test_bez_utoku_sekcia_nie_je(self):
        assert "DRZÝ" not in self._prompt(False)


class TestRozlucka:
    """Posledná správa v chate — musí povedať PREČO a KAM, nie len zmiznúť."""

    @staticmethod
    def _prompt(allow_link=True, link_already_sent=False, farewell=True):
        persona = {
            "name": "Simona", "language": "", "languages": "",
            "lang_primary": "en", "lang_extra": [],
            "backstory": "", "tone": "", "msg_style": "",
            "boundaries": "", "funnel_rules": "",
            "cta_link": "https://fanvue.com/simona", "extra_rules": "",
        }
        return build_system_prompt(
            persona,
            {"tg_id": 1, "msg_count": 30, "funnel_stage": "warm"},
            allow_link=allow_link,
            asked_if_ai=False,
            farewell=farewell,
            link_already_sent=link_already_sent,
        )

    def test_vie_ze_je_to_posledna_sprava(self):
        out = self._prompt()
        assert "POSLEDNÁ SPRÁVA" in out

    def test_odkaz_ide_do_nej(self):
        """Pozvánka bez adresy je len rozlúčka."""
        assert "https://fanvue.com/simona" in self._prompt()

    def test_ked_odkaz_uz_ma_len_pripomenie(self):
        out = self._prompt(allow_link=False, link_already_sent=True)
        assert "PRIPOMEŇ" in out
        assert "https://fanvue.com/simona" not in out

    def test_nadviaze_na_rozhovor(self):
        """Napísaná fráza by prezradila automat viac než čokoľvek iné."""
        out = self._prompt()
        assert "VLASTNÝMI SLOVAMI" in out
        assert "zareaguj na to, čo ti práve napísal" in out

    def test_bez_rozlucky_tam_nic_z_toho_nie_je(self):
        out = self._prompt(farewell=False)
        assert "POSLEDNÁ SPRÁVA" not in out
