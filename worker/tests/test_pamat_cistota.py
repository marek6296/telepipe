"""Čistota pamäte — všetko, čo vzniklo z merania na živých dátach.

Meranie ukázalo tri veci naraz: sudca opravoval 48 % odpovedí a 89 % tých
opráv bolo opakovanie; v tabuľke faktov ležal ten istý údaj pod dvoma kľúčmi;
a ako trvalý fakt bolo uložené, čo klient práve robil. Tieto testy držia
každú z tých troch opráv na mieste.
"""
import asyncio

import facts
import humanize
import similar
import judge
import persona

similar_same = similar.same_idea


# ---------- fakty: uzavreté kľúče ----------

class TestKlucSaZjednoti:
    def test_synonymne_kluce_koncia_rovnako(self):
        assert facts.canonical_key("past_locations") == "past"
        assert facts.canonical_key("previous_locations") == "past"
        assert facts.canonical_key("job") == "work"
        assert facts.canonical_key("occupation") == "work"
        assert facts.canonical_key("equipment") == "tech"
        assert facts.canonical_key("tools") == "tech"
        assert facts.canonical_key("wants") == "values"
        assert facts.canonical_key("tv_shows") == "hobbies"

    def test_povoleny_kluc_ostane(self):
        for key in facts.TOPIC_KEYS:
            assert facts.canonical_key(key) == key

    def test_vymysleny_kluc_skonci_ako_other(self):
        assert facts.canonical_key("truck_route_number") == "other"
        assert facts.canonical_key("") == "other"

    def test_kluc_sa_ocisti(self):
        assert facts.canonical_key("  Work  ") == "work"
        assert facts.canonical_key("JOB") == "work"


class TestOkamihNieJeFakt:
    """„leží na gauči a pozerá seriál" bolo naživo uložené pod štyrmi kľúčmi."""

    def test_kluc_okamihu_prepadne(self):
        assert facts.is_transient("current_activity", "watching a show")
        assert facts.is_transient("activity", "čokoľvek")
        assert facts.is_transient("weekend", "went by too fast")

    def test_znenie_okamihu_prepadne_aj_pod_dobrym_klucom(self):
        assert facts.is_transient("location", "on the couch watching a show and texting")
        assert facts.is_transient("time", "it's still early for him")
        assert facts.is_transient("hobbies", "just finished the season")

    def test_skutocny_fakt_prejde(self):
        assert not facts.is_transient("work", "vodič kamiónu, jazdí po západnom pobreží")
        assert not facts.is_transient("past", "vyrastal v lesoch v Michigane")
        assert not facts.is_transient("pets", "má psa Bruna")

    def test_extraktor_okamihy_zahodi(self):
        raw = """[
          {"key": "work", "value": "truck driver"},
          {"key": "current_activity", "value": "on the couch"},
          {"key": "location", "value": "laying on the couch right now"}
        ]"""
        out = facts._coerce(raw)
        assert out == [{"key": "work", "value": "truck driver"}]

    def test_extraktor_zjednoti_kluc(self):
        out = facts._coerce('[{"key": "previous_locations", "value": "lived in Reno"}]')
        assert out == [{"key": "past", "value": "lived in Reno"}]

    def test_dva_kluce_o_tom_istom_v_jednej_davke(self):
        raw = """[
          {"key": "equipment", "value": "uses a power washer, hose broke"},
          {"key": "tools", "value": "usually uses power washer; needs new hose"}
        ]"""
        assert len(facts._coerce(raw)) == 1


class TestZlucovanieFaktov:
    STARE = [
        {"id": 1, "key": "past", "value": "used to live in Sacramento", "superseded_by": None},
        {"id": 2, "key": "work", "value": "vodič kamiónu", "superseded_by": None},
    ]

    def test_parafraza_pod_inym_klucom_sa_potvrdi_a_nezalozi(self):
        plan = facts.merge_plan(
            self.STARE, [{"key": "location", "value": "used to live in Sacramento"}]
        )
        assert plan["inserts"] == []
        assert plan["confirms"] == [1]

    def test_zmena_pod_znamym_klucom_stare_odlozi(self):
        plan = facts.merge_plan(self.STARE, [{"key": "work", "value": "robí v sklade"}])
        assert plan["supersedes"] == [2]
        assert len(plan["inserts"]) == 1

    def test_naozaj_novy_fakt_pribudne(self):
        plan = facts.merge_plan(self.STARE, [{"key": "pets", "value": "má psa Bruna"}])
        assert plan["inserts"] == [{"key": "pets", "value": "má psa Bruna"}]
        assert plan["confirms"] == [] and plan["supersedes"] == []

    def test_dve_nove_o_tom_istom_prejdu_raz(self):
        """Presne ten prípad z databázy: `equipment` a `tools` s tou istou vecou."""
        plan = facts.merge_plan(
            [],
            [
                {"key": "equipment", "value": "uses a power washer, hose broke"},
                {"key": "tools", "value": "usually uses power washer, needs new hose"},
            ],
        )
        assert len(plan["inserts"]) == 1

    def test_sklonovane_meno_sa_nezachyti_a_je_to_tak_spravne(self):
        """Vedomý kompromis, nie prehliadnutie.

        „má psa Bruna" a „má psa, volá sa Bruno" prejdú ako dva fakty, lebo
        koreň slova je päť znakov a „bruna"/„bruno" sa naň nezmestia. Skrátenie
        na štyri znaky by ich zlúčilo — ale zároveň by zlúčilo „sestru" so
        „sesternicou". Falošné zlúčenie ticho zmaže skutočný fakt, zatiaľ čo
        prehliadnutá duplicita len zaberie riadok. Preto radšej duplicita.
        """
        assert not similar_same("má sestru", "má sesternicu")
        plan = facts.merge_plan(
            [],
            [
                {"key": "pets", "value": "má psa Bruna"},
                {"key": "other", "value": "má psa, volá sa Bruno"},
            ],
        )
        assert len(plan["inserts"]) == 2


class TestFactSheet:
    def test_parafrazy_sa_do_promptu_nedostanu(self):
        rows = [
            {"key": "home", "value": "žije sama", "superseded_by": None},
            {"key": "other", "value": "býva sama", "superseded_by": None},
            {"key": "music", "value": "počúva rock", "superseded_by": None},
        ]
        out = facts.sheet(rows)
        assert out.count("sama") == 1
        assert "počúva rock" in out

    def test_stary_okamih_z_databazy_sa_uz_nezobrazi(self):
        rows = [
            {"key": "location", "value": "on the couch watching a show",
             "superseded_by": None},
            {"key": "work", "value": "vodič kamiónu", "superseded_by": None},
        ]
        out = facts.sheet(rows)
        assert "couch" not in out
        assert "kamiónu" in out

    def test_zoznam_ma_strop(self):
        rows = [
            {"key": "other", "value": f"úplne odlišná vec číslo {i}", "superseded_by": None}
            for i in range(60)
        ]
        assert len(facts.sheet(rows).splitlines()) <= facts.SHEET_LIMIT


class TestZnameTemy:
    def test_okamih_pod_klucom_temy_temu_nezamkne(self):
        """Naživo `location` = „on the couch" a otázka odkiaľ je bola navždy preč."""
        rows = [{"key": "location", "value": "on the couch watching a show",
                 "superseded_by": None}]
        assert facts.known_keys(rows) == []

    def test_skutocna_odpoved_temu_zamkne(self):
        rows = [{"key": "location", "value": "žije v Ohiu", "superseded_by": None}]
        assert facts.known_keys(rows) == ["location"]


# ---------- tvrdenia o sebe ----------

class TestTvrdeniaOSebe:
    def test_parafrazy_sa_do_promptu_nedostanu(self):
        rows = [
            {"claim": "má tetovanie"},
            {"claim": "je tetovaná"},
            {"claim": "má Fanvue stránku sima.sima"},
            {"claim": "má stránku na Fanvue"},
        ]
        out = judge.claims_block(rows)
        assert len(out.splitlines()) == 2

    def test_prazdne_ostane_prazdne(self):
        assert judge.claims_block([]) == ""

    def test_novy_zapis_preskoci_parafrazu(self):
        class FakeDb:
            def __init__(self):
                self.pridane = []

            async def self_claims(self, tg_id, limit=12):
                return [{"claim": "má tetovanie"}]

            async def add_self_claim(self, tg_id, claim):
                self.pridane.append(claim)

        class FakeLlm:
            async def structured(self, system, content, **kw):
                return '["je tetovaná", "má brata v Texase"]'

        db = FakeDb()
        asyncio.run(
            judge.sync_claims(
                FakeLlm(), db, 1,
                [{"role": "assistant", "content": "x", "created_at": None}],
                "Simona",
            )
        )
        assert db.pridane == ["má brata v Texase"]


# ---------- opakovanie: pisateľ dostane zoznam ----------

class TestPisatelViCoUzPovedala:
    @staticmethod
    def _prompt(**kw):
        return persona.build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 30, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, **kw,
        )

    def test_jej_spravy_su_v_prompte(self):
        out = self._prompt(her_recent=["haha ty si vtipny", "mne je zima furt"])
        assert "TOTO SI UŽ POVEDALA" in out
        assert "haha ty si vtipny" in out
        assert "mne je zima furt" in out

    def test_zoznam_je_az_na_konci(self):
        """Model drží koniec promptu najlepšie — preto tam patrí."""
        out = self._prompt(her_recent=["nieco tu"])
        assert out.index("TOTO SI UŽ POVEDALA") > len(out) * 0.7

    def test_bez_historie_sa_sekcia_nepridava(self):
        assert "TOTO SI UŽ POVEDALA" not in self._prompt()
        assert "TOTO SI UŽ POVEDALA" not in self._prompt(her_recent=["", "   "])

    def test_berie_sa_poslednych_sest(self):
        out = self._prompt(her_recent=[f"sprava cislo {i}" for i in range(12)])
        assert "sprava cislo 11" in out
        assert "sprava cislo 5" not in out


class TestOtazkaVRanejFaze:
    @staticmethod
    def _prompt(msg_count, **kw):
        import topics
        return persona.build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": msg_count, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False,
            can_ask=True, fresh_topics=[topics.BY_KEY["work"]], **kw,
        )

    def test_na_zaciatku_je_otazka_prikaz(self):
        out = self._prompt(6)
        assert "SPÝTAJ SA HO NA JEDNU VEC" in out

    def test_neskor_je_to_len_moznost(self):
        out = self._prompt(40)
        assert "SPÝTAJ SA HO NA JEDNU VEC" not in out
        assert "Môžeš sa spýtať JEDNU vec" in out


# ---------- otvárače ----------

class TestOpakovanyOtvarac:
    def test_treti_haha_za_sebou_prijde_o_haha(self):
        out = humanize.thin_openers(
            "haha to je dobre", ["haha ty si vtipny", "haha no vidis"]
        )
        assert not out.lower().startswith("haha")
        assert "to je dobre" in out

    def test_dva_za_sebou_este_prejdu(self):
        text = "haha to je dobre"
        assert humanize.thin_openers(text, ["haha ty si vtipny", "yeah no"]) == text

    def test_iny_otvarac_sa_nedotkne(self):
        text = "yeah presne tak"
        assert humanize.thin_openers(text, ["haha jeden", "haha dva"]) == text

    def test_kratka_sprava_sa_neodstreli(self):
        """Keby po odstránení nezostalo nič, je lepšie nechať opakovaný začiatok."""
        text = "haha"
        assert humanize.thin_openers(text, ["haha aa", "haha bb"]) == text

    def test_bez_historie_sa_nic_nedeje(self):
        text = "haha to je dobre"
        assert humanize.thin_openers(text, []) == text

    def test_opener_cita_prve_slovo(self):
        assert humanize.opener("haha, to je dobre") == "haha"
        assert humanize.opener("  Yeah no") == "yeah"
        assert humanize.opener("😅 nic") == ""
