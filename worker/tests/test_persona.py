"""Systémový prompt — jazyková politika modeliek."""
from persona import build_system_prompt


class TestJazyky:
    """Anglicky s každým, ale kto napíše jazykom, ktorý vie, dostane odpoveď v ňom."""

    @staticmethod
    def _prompt(languages="", foreign=False):
        persona = {
            "name": "Simona", "language": "English by default.",
            "languages": languages, "backstory": "", "tone": "", "msg_style": "",
            "boundaries": "", "funnel_rules": "", "cta_link": "", "extra_rules": "",
        }
        return build_system_prompt(
            persona, {"tg_id": 1, "msg_count": 7, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, foreign=foreign,
        )

    def test_zoznam_jazykov_je_v_prompte(self):
        out = self._prompt("Slovak fluent. German basic B1.")
        assert "Slovak fluent" in out and "ČO OVLÁDAŠ ZA JAZYKY" in out

    def test_cudzi_jazyk_smie_odpovedat_v_nom(self):
        out = self._prompt("Slovak fluent.", foreign=True)
        assert "V TOM JAZYKU" in out

    def test_bez_zoznamu_ostava_len_anglictina(self):
        """Modelka bez vyplnených jazykov sa nesmie zrazu tváriť, že vie po nemecky."""
        out = self._prompt("", foreign=True)
        assert "hovoríš len po anglicky" in out and "V TOM JAZYKU" not in out

    def test_neznamy_jazyk_prizna(self):
        out = self._prompt("Slovak fluent.", foreign=True)
        assert "jazyk, ktorý neovládaš" in out

    def test_zoznam_nema_zvadzat_ku_klamstvu(self):
        out = self._prompt("Slovak fluent.")
        assert "Nikdy netvrď, že vieš jazyk, ktorý tu nie je" in out


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
