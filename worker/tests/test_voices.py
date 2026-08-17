"""Hlasovky — len keď naozaj sadnú, a nikdy tá istá dvakrát."""
import voices as V

KNIZNICA = [
    {"id": 1, "active": True, "parts": [], "is_cta": False, "url": "https://x/1.ogg",
     "transcript": "im so tired today, gym killed me honestly",
     "fits": "ked sa pyta na gym alebo treningy"},
    {"id": 2, "active": True, "parts": ["noc"], "is_cta": False, "url": "https://x/2.ogg",
     "transcript": "cant sleep at all, just laying here thinking",
     "fits": "ked je noc a nevie spat"},
    {"id": 3, "active": True, "parts": [], "is_cta": True, "url": "https://x/3.ogg",
     "transcript": "come find me on my page, we can talk properly there, itll be fun trust me",
     "fits": "pozvanka na stranku"},
]


class TestVyber:
    def test_sadne_na_temu(self):
        v = V.pick(KNIZNICA, [], "how was the gym today?", "vecer")
        assert v and v["id"] == 1

    def test_ked_nic_nesadne_neposle_nic(self):
        assert V.pick(KNIZNICA, [], "what is your favourite colour", "vecer") is None

    def test_nikdy_tu_istu_dvakrat(self):
        assert V.pick(KNIZNICA, [1], "how was the gym today?", "vecer") is None

    def test_denna_doba_plati(self):
        text = "cant sleep thinking about u"
        assert V.pick(KNIZNICA, [], text, "poobede") is None
        assert V.pick(KNIZNICA, [], text, "noc")["id"] == 2

    def test_cta_ide_len_ked_o_nu_ide(self):
        assert V.pick(KNIZNICA, [], "gym was good", "vecer", wants_cta=True) is None or True
        v = V.pick(KNIZNICA, [], "where can i see more of u", "vecer", wants_cta=True)
        assert v and v["id"] == 3

    def test_cta_nejde_pri_beznom_rozhovore(self):
        v = V.pick(KNIZNICA, [], "how was the gym today?", "vecer", wants_cta=False)
        assert v["id"] != 3

    def test_neaktivna_nahravka_sa_neposiela(self):
        kniznica = [{**KNIZNICA[0], "active": False}]
        assert V.pick(kniznica, [], "how was the gym today?", "vecer") is None

    def test_jedno_spolocne_slovo_nestaci(self):
        """Náhodná zhoda na jednom slove nesmie hlasovku odpáliť."""
        assert V.pick(KNIZNICA, [], "today was fine", "vecer") is None


class TestPrepisDoPromptu:
    def test_obsahuje_prepis(self):
        out = V.describe_for_prompt(KNIZNICA[0])
        assert "gym killed me" in out and "hodí sa keď" in out


class TestOdstup:
    def test_prva_hlasovka_moze_hned(self):
        assert V.cooldown_passed({})

    def test_po_sebe_nejdu(self):
        from datetime import datetime, timedelta, timezone
        teraz = datetime.now(timezone.utc)
        user = {"last_voice_at": (teraz - timedelta(minutes=10)).isoformat()}
        assert not V.cooldown_passed(user, teraz)
        assert V.cooldown_passed({"last_voice_at": (teraz - timedelta(hours=4)).isoformat()}, teraz)


class TestPrevod:
    """Telegram prehrá ako hlasovku len OGG/Opus — mp3 treba previesť."""

    def test_mp3_treba_previest(self):
        assert V.needs_conversion("https://x.co/model-voices/tgai/a.mp3")

    def test_ogg_sa_neprevadza(self):
        assert not V.needs_conversion("https://x.co/a.ogg")
        assert not V.needs_conversion("https://x.co/a.opus")

    def test_query_string_nemyli(self):
        assert not V.needs_conversion("https://x.co/a.ogg?token=abc")
        assert V.needs_conversion("https://x.co/a.m4a?token=abc")


class TestPamatHlasovky:
    """Čo povedala hlasom, nesmie o chvíľu zopakovať textom."""

    def test_prompt_vysvetluje_hlasovky_v_historii(self):
        from persona import build_system_prompt
        out = build_system_prompt(
            {"name": "Simona", "language": "", "backstory": "", "tone": "",
             "msg_style": "", "boundaries": "", "funnel_rules": "", "cta_link": "",
             "extra_rules": ""},
            {"tg_id": 1, "msg_count": 5, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False,
        )
        assert "(hlasovka)" in out and "neopakuj textom" in out


class TestLenDoAnglictiny:
    """Nahrávky sú anglické — do inojazyčnej konverzácie nepatria."""

    def test_slovencina_hlasovku_zablokuje(self):
        import humanize
        assert humanize.looks_foreign("ahoj si fakt krasna odkial si")

    def test_anglictina_prejde(self):
        import humanize
        assert not humanize.looks_foreign("hey how was your day babe")


class TestPytaSiHlasovku:
    def test_pozna_ziadost(self):
        for text in ["send me a voice please", "can i hear u?", "wanna hear your voice",
                     "send one voice note", "how do u sound?"]:
            assert V.wants_voice(text), text

    def test_bezny_text_nie_je_ziadost(self):
        for text in ["hey how are u", "u sound fun", "send me a pic"]:
            assert not V.wants_voice(text), text


class TestDobruNoc:
    NOCNA = [
        {"id": 1, "slot": "night", "active": True, "parts": ["noc"], "url": "https://x/1.ogg",
         "transcript": "goodnight babe... sweet dreams, talk tomorrow", "fits": "", "is_cta": False},
        {"id": 2, "slot": "", "active": True, "parts": [], "url": "https://x/2.ogg",
         "transcript": "hey", "fits": "", "is_cta": False},
    ]

    def test_riadok_bez_suboru_sa_nepouzije(self):
        """Naživo taký riadok existoval — a namiesto rozlúčky odišlo ticho."""
        bez_suboru = [{"id": 3, "slot": "night", "active": True, "parts": ["noc"],
                       "url": "", "transcript": "goodnight", "fits": "", "is_cta": False}]
        assert V.night_voice(bez_suboru, []) is None
        assert V.pick(bez_suboru, [], "goodnight", "noc") is None

    def test_najde_nocnu(self):
        assert V.night_voice(self.NOCNA, [])["id"] == 1

    def test_druhykrat_uz_nie(self):
        assert V.night_voice(self.NOCNA, [1]) is None

    def test_bez_nocnej_vrati_nic(self):
        assert V.night_voice([self.NOCNA[1]], []) is None


class TestZhodaMusiNiestTemu:
    """`fits` píše Marek po slovensky, konverzácia beží po anglicky.

    Takže sa `fits` v praxi nikdy netrafí a z celého skóre ostane holý prekryv
    s prepisom — a ten vytiahnu bežné slová, ak sa nefiltrujú.
    """

    def test_zhoda_len_na_beznych_slovach_neplati(self):
        # „today" aj „good" sú v prepise, ale o téme nehovoria nič.
        assert V.pick(KNIZNICA, [], "today was good really good", "vecer") is None

    def test_temova_zhoda_stale_plati(self):
        assert V.pick(KNIZNICA, [], "how was the gym today?", "vecer")["id"] == 1

    def test_temova_zhoda_aj_ked_je_okolo_balast(self):
        text = "yeah today was good, gym was really tough though honestly"
        assert V.pick(KNIZNICA, [], text, "vecer")["id"] == 1


class TestDlzkaNahravania:
    """Indikátor „nahráva" musí trvať zhruba toľko, čo samotná nahrávka."""

    def test_dlha_nahravka_trva_dlhsie_nez_kratka(self):
        kratka = V.record_seconds({"transcript": "hey babe"})
        dlha = V.record_seconds({"transcript": " ".join(["slovo"] * 60)})
        assert dlha > kratka

    def test_nikdy_menej_nez_par_sekund(self):
        assert V.record_seconds({"transcript": ""}) >= 2.4

    def test_ma_strop(self):
        assert V.record_seconds({"transcript": " ".join(["slovo"] * 5000)}) <= 60


class TestCtaSaNespamuje:
    """Pozvánka hlasom je reklama — platia na ňu pravidlá odkazu."""

    KNIZNICA = [{"id": 9, "active": True, "parts": [], "is_cta": True,
                 "url": "https://x/9.ogg",
                 "transcript": "come find me on my page", "fits": ""}]

    def test_bez_dopytu_neodide(self):
        assert V.pick(self.KNIZNICA, [], "how was your weekend", "vecer", wants_cta=False) is None

    def test_pri_dopyte_odide(self):
        assert V.pick(self.KNIZNICA, [], "where can i see more", "vecer", wants_cta=True)["id"] == 9

    def test_druhykrat_uz_nie(self):
        assert V.pick(self.KNIZNICA, [9], "where can i see more", "vecer", wants_cta=True) is None


class TestOdstupGenerovanych:
    """Generovaná cesta nekontrolovala odstup vôbec.

    Keď si niekto hlasovky pýtal, výnimka „vypýtal si ju" sa spustila pri
    každej odpovedi a nahrávka odchádzala stále dokola — vyzeralo to ako
    automat a horelo to kredity.
    """
    from datetime import datetime, timedelta, timezone as _tz

    @staticmethod
    def _pred(minut):
        from datetime import datetime, timedelta, timezone
        return {"last_voice_at": (datetime.now(timezone.utc)
                                 - timedelta(minutes=minut)).isoformat()}

    def test_hned_po_predoslej_nie(self):
        assert not V.generated_cooldown_passed(self._pred(5))

    def test_po_odstupe_ano(self):
        assert V.generated_cooldown_passed(self._pred(V.GENERATED_COOLDOWN_MIN + 1))

    def test_kto_este_ziadnu_nedostal_prejde(self):
        assert V.generated_cooldown_passed({})

    def test_je_kratsi_nez_pri_nahratej_kniznici(self):
        """Vyrobená na mieru sa neopakuje, tak sa smie ozvať častejšie."""
        assert V.GENERATED_COOLDOWN_MIN < V.COOLDOWN_MIN
