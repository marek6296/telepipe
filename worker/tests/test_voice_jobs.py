"""Fronta na ukážky a archív vyrobených hlasoviek.

Worker na Railway nemá port, takže si dashboard nemá kam zavolať — požiadavka
chodí riadkom v databáze. Tieto testy strážia, že sa práca nestratí ani
nespracuje dvakrát a že zlyhanie skončí zapísanou chybou, nie tichom.
"""
import asyncio

import pytest
from config import TenantConfig as Config
from userbot import UserBot

pytestmark = pytest.mark.usefixtures("fast")


def make_config(**overrides):
    base = dict(
        model_id="test-model", account_id="acc-1", name="Lucia",
        tg_api_id=1, tg_api_hash="hash", tg_session="sess",
        control_bot_token="token", owner_chat_id=999, owner_as_client=False,
        supabase_schema="tgai",
        llm_key="key", llm_base_url="https://x/v1", model="m", summary_model="m",
        reasoning_effort="low", vision_model="v", audio_model="a",
        context_messages=12, summary_every=15, skip_contacts=True,
        contact_exceptions=frozenset(), link_min_messages=6,
        link_cooldown_hours=48, link_max_pushes=3,
    )
    base.update(overrides)
    return Config(**base)


class FakeDb:
    def __init__(self, job=None, behavior=None):
        self.job = job
        self.claimed = []
        self.finished = []
        self.clips = []
        self.uploads = []
        self.behavior = behavior or {
            "eleven_key": "k", "eleven_voice_id": "v",
            "voice_ambience": "home", "voice_strength": "real",
            "voice_tempo": 1.12, "voice_ambience_level": 0.05,
        }

    async def pending_voice_job(self):
        return self.job

    async def claim_voice_job(self, job_id):
        self.claimed.append(job_id)
        # Druhýkrát tú istú prácu už nikto nedostane.
        return self.claimed.count(job_id) == 1

    async def finish_voice_job(self, job_id, url="", error=""):
        self.finished.append({"id": job_id, "url": url, "error": error})

    async def get_behavior(self):
        return dict(self.behavior)

    async def upload_voice(self, path, data):
        self.uploads.append((path, len(data)))
        return f"https://x/{path}"

    async def add_voice_clip(self, row):
        self.clips.append(row)
        return row


class FakeLlm:
    async def structured(self, *_a, **_k):
        return "hej no proste dneska bol dlhy den"


def build(job, speak_returns=b"OGGDATA", monkeypatch=None):
    import livevoice

    db = FakeDb(job)
    bot = UserBot(make_config(), db, FakeLlm(), None, None)

    async def fake_speak(*_a, **_k):
        return speak_returns

    monkeypatch.setattr(livevoice, "speak", fake_speak)
    return bot, db


class TestFrontaUkazok:
    JOB = {
        "id": 7, "text": "hey im just laying here doing nothing",
        "voice_id": "hlas", "eleven_key": "kluc",
        "ambience": "gym", "strength": "rough",
        "tempo": 1.2, "ambience_level": 0.08,
    }

    def test_vyrobi_ulozi_a_dopise_adresu(self, monkeypatch):
        bot, db = build(dict(self.JOB), monkeypatch=monkeypatch)
        asyncio.run(bot._voice_jobs_once())

        assert db.finished == [{"id": 7, "url": "https://x/tgai/generated/"
                                + db.uploads[0][0].split("/")[-1], "error": ""}]
        assert db.uploads and db.uploads[0][0].startswith("tgai/generated/")
        assert db.clips[0]["kind"] == "preview"
        assert db.clips[0]["ambience"] == "gym"

    def test_prazdna_fronta_nic_nerobi(self, monkeypatch):
        bot, db = build(None, monkeypatch=monkeypatch)
        asyncio.run(bot._voice_jobs_once())
        assert not db.finished and not db.uploads

    def test_pracu_si_vezme_len_jeden(self, monkeypatch):
        bot, db = build(dict(self.JOB), monkeypatch=monkeypatch)
        asyncio.run(bot._voice_jobs_once())
        asyncio.run(bot._voice_jobs_once())
        assert len(db.finished) == 1, "druhý beh tú istú prácu nesmie zopakovať"

    def test_ked_sa_nahravka_nevyrobi_zapise_sa_chyba(self, monkeypatch):
        bot, db = build(dict(self.JOB), speak_returns=None, monkeypatch=monkeypatch)
        asyncio.run(bot._voice_jobs_once())
        assert db.finished[0]["error"], "ticho by dashboard nechalo čakať donekonečna"
        assert not db.finished[0]["url"]

    def test_pad_pri_vyrobe_skonci_zapisanou_chybou(self, monkeypatch):
        import livevoice

        db = FakeDb(dict(self.JOB))
        bot = UserBot(make_config(), db, FakeLlm(), None, None)

        async def boom(*_a, **_k):
            raise RuntimeError("ffmpeg chyba")

        monkeypatch.setattr(livevoice, "speak", boom)
        asyncio.run(bot._voice_jobs_once())
        assert "ffmpeg" in db.finished[0]["error"]

    def test_ukazka_sa_nikomu_neposiela(self, monkeypatch):
        """Ukážka je na počúvanie v dashboarde, nie na doručenie fanúšikovi."""
        bot, db = build(dict(self.JOB), monkeypatch=monkeypatch)
        odoslane = []
        monkeypatch.setattr(
            bot, "_send_generated_voice",
            lambda *a, **k: odoslane.append(a),
        )
        asyncio.run(bot._voice_jobs_once())

        assert not odoslane, "preview nesmie skončiť v žiadnom chate"
        assert db.clips[0]["tg_id"] is None, "ukážka nepatrí žiadnemu človeku"
        assert db.clips[0]["kind"] == "preview"


class TestUkazkaVieCoZaznelo:
    """Zoznam ukážok má hovoriť pravdu o tom, čo je v nich počuť.

    Kým sa nastavenia brali z práce len pri VÝROBE a do archívu sa písalo
    uložené chovanie, klient si posunul tempo, vypočul si zmenu — a v zozname
    mal pri oboch ukážkach to isté číslo. A/B ladenie tým stratilo zmysel.
    """

    JOB = dict(TestFrontaUkazok.JOB)

    def test_archiv_nesie_nastavenie_z_prace_nie_ulozene(self, monkeypatch):
        bot, db = build(dict(self.JOB), monkeypatch=monkeypatch)
        asyncio.run(bot._voice_jobs_once())

        zapis = db.clips[0]
        assert zapis["ambience"] == "gym", "uložené je 'home'"
        assert zapis["strength"] == "rough", "uložené je 'real'"
        assert float(zapis["tempo"]) == 1.2, "uložené je 1.12"
        assert zapis["voice_id"] == "hlas", "uložený je 'v'"

    def test_vyroba_dostane_to_iste_co_archiv(self, monkeypatch):
        import livevoice

        db = FakeDb(dict(self.JOB))
        bot = UserBot(make_config(), db, FakeLlm(), None, None)
        zachytene = {}

        async def fake_speak(text, key, voice, ambience, strength, **kw):
            zachytene.update(
                key=key, voice=voice, ambience=ambience, strength=strength, **kw
            )
            return b"OGG"

        monkeypatch.setattr(livevoice, "speak", fake_speak)
        asyncio.run(bot._voice_jobs_once())

        zapis = db.clips[0]
        assert zachytene["ambience"] == zapis["ambience"]
        assert zachytene["strength"] == zapis["strength"]
        assert zachytene["tempo"] == float(zapis["tempo"])
        assert zachytene["voice"] == zapis["voice_id"]
        assert zachytene["level"] == 0.08, "hlasitosť pozadia z práce"

    def test_prazdne_polia_v_praci_padnu_na_ulozene(self, monkeypatch):
        prazdna = dict(self.JOB, ambience="", strength="", tempo=0,
                       ambience_level=0, voice_id="", eleven_key="")
        bot, db = build(prazdna, monkeypatch=monkeypatch)
        asyncio.run(bot._voice_jobs_once())

        zapis = db.clips[0]
        assert zapis["ambience"] == "home"
        assert zapis["strength"] == "real"
        assert float(zapis["tempo"]) == 1.12
        assert zapis["voice_id"] == "v"


class TestPrecoUkazkaNevznikla:
    """Dashboard potrebuje vetu, nie ticho — a rozlíšiteľnú.

    „Nepodarilo sa" na chýbajúci hlas je najhoršia možná odpoveď: klient to
    má na jeden preklik a nevie o tom.
    """

    JOB = dict(TestFrontaUkazok.JOB, voice_id="", eleven_key="")

    def test_bez_kluca_povie_ze_chyba_kluc(self, monkeypatch):
        import userbot as U

        bot, db = build(dict(self.JOB), monkeypatch=monkeypatch)
        db.behavior["eleven_key"] = ""
        asyncio.run(bot._voice_jobs_once())

        assert db.finished[0]["error"] == U.VOICE_JOB_NO_KEY
        assert not db.uploads, "bez kľúča sa nemá čo vyrábať ani ukladať"

    def test_bez_hlasu_povie_ze_chyba_hlas(self, monkeypatch):
        import userbot as U

        bot, db = build(dict(self.JOB), monkeypatch=monkeypatch)
        db.behavior["eleven_voice_id"] = ""
        asyncio.run(bot._voice_jobs_once())

        assert db.finished[0]["error"] == U.VOICE_JOB_NO_VOICE

    def test_ked_nevznikol_zvuk_je_to_vlastny_kod(self, monkeypatch):
        import userbot as U

        bot, db = build(dict(TestFrontaUkazok.JOB), speak_returns=None,
                        monkeypatch=monkeypatch)
        asyncio.run(bot._voice_jobs_once())

        assert db.finished[0]["error"] == U.VOICE_JOB_NO_AUDIO

    def test_kody_su_rozlisitelne(self):
        import userbot as U

        kody = {U.VOICE_JOB_NO_KEY, U.VOICE_JOB_NO_VOICE, U.VOICE_JOB_NO_AUDIO}
        assert len(kody) == 3
        # Web ich prekladá podľa presnej zhody — medzery ani veľké písmená
        # by tú zhodu ticho rozbili.
        assert all(k == k.strip().lower() and " " not in k for k in kody)


class TestArchiv:
    def test_zapise_co_a_odkial_znelo(self, monkeypatch):
        from behavior import Behavior

        db = FakeDb()
        bot = UserBot(make_config(), db, FakeLlm(), None, None)
        url = asyncio.run(
            bot._archive_voice(
                555, b"data", text="hey there", spoken="hey there [laughs]",
                ambience="car", behavior=Behavior(voice_strength="rough"),
            )
        )
        assert url.startswith("https://x/tgai/generated/")
        zapis = db.clips[0]
        assert zapis["tg_id"] == 555
        assert zapis["text"] == "hey there"
        assert zapis["spoken"] == "hey there [laughs]"
        assert zapis["ambience"] == "car"
        assert zapis["kind"] == "reply"

    def test_zlyhanie_uloziska_nezhodi_odpoved(self, monkeypatch):
        from behavior import Behavior

        db = FakeDb()

        async def boom(*_a, **_k):
            raise RuntimeError("úložisko nedostupné")

        db.upload_voice = boom
        bot = UserBot(make_config(), db, FakeLlm(), None, None)
        # Nesmie vyhodiť — hlasovka klientovi už odišla.
        assert asyncio.run(
            bot._archive_voice(1, b"d", text="t", spoken="s", ambience="home",
                               behavior=Behavior())
        ) == ""


class TestMiestnostiZniaInak:
    """Rovnaké filtre pre všetky miestnosti boli chyba.

    Spálňa je dunenie za stenou a patrí hlboko pod hlas; ulica je okolo teba.
    Keď sa oreže rovnako, znie ulica ako tá istá spálňa.
    """

    def test_ulica_je_hlasnejsia_a_sirsia_nez_spalna(self):
        import livevoice as L

        ulica_hl, _, ulica_hore = L.ambience_mix("outside", 0.05)
        spalna_hl, _, spalna_hore = L.ambience_mix("bedroom", 0.05)
        assert ulica_hl > spalna_hl
        assert ulica_hore > spalna_hore

    def test_auto_dune_nizsie_nez_kupelna(self):
        import livevoice as L

        _, auto_dole, _ = L.ambience_mix("car", 0.05)
        _, kupelna_dole, _ = L.ambience_mix("bathroom", 0.05)
        assert auto_dole < kupelna_dole, "motor je dole, kachličky nesú výšky"

    def test_ticho_nema_hlasitost(self):
        import livevoice as L

        assert L.ambience_mix("none", 0.05)[0] == 0.0

    def test_nastavenie_stale_plati_ako_zaklad(self):
        import livevoice as L

        ticho = L.ambience_mix("gym", 0.02)[0]
        hlasno = L.ambience_mix("gym", 0.10)[0]
        assert hlasno > ticho, "posuvník v dashboarde musí mať vplyv"

    def test_neznama_miestnost_nespadne(self):
        import livevoice as L

        assert L.ambience_mix("vesmir", 0.05) == L.ambience_mix("home", 0.05)


class TestHlasitostHlasu:
    """Stíšenie hlasu sa nesmie dotknúť pozadia.

    `volume` na konci reťazca beží až na celom mixe, takže by stiahol aj
    miestnosť. Preto sa hlas stišuje na vlastnej vetve pred zmiešaním.
    """

    def test_stisenie_a_kolisanie_nie_su_na_mixe(self):
        """Vzdialenosť od úst sa mení, izba okolo zostáva rovnaká.

        Kým bolo kolísanie na mixe, hýbalo sa aj pozadie — a to je fyzikálny
        nezmysel: ruka s telefónom nemôže stíšiť celú miestnosť. Reťazec mixu
        preto nesmie obsahovať ani stíšenie hlasu, ani kolísanie.
        """
        import livevoice as L

        _, chain, _, _ = L._chain("real", 1.12, volume=0.6)
        assert str(L.VOICE_GAIN) not in chain, "na mixe by to stiahlo aj pozadie"
        assert "sin(" not in chain, "miestnosť kolísať nesmie"

    def test_vyraz_pre_hlas_nesie_stisenie_aj_kolisanie(self):
        import livevoice as L

        vyraz = L.volume_expression([(2.0, 0.2, 0.3)], drift_period=7.0)
        assert str(L.VOICE_GAIN) in vyraz
        assert "sin(" in vyraz and "7.00" in vyraz
        assert "exp(" in vyraz, "pokles je zvon, nie schod"

    def test_hlas_znie_ako_z_telefonu_nie_zo_studia(self):
        import livevoice as L

        mic, _, _, _ = L._chain("real", 1.12)
        assert "highpass=f=140" in mic, "telefón nesníma dunenie zdola"
        assert "f=250" in mic, "blízke snímanie robí krabicu okolo 250 Hz"

    def test_pozadie_na_stisenie_hlasu_nereaguje(self):
        import livevoice as L

        pred = L.ambience_mix("gym", 0.05)
        povodne = L.VOICE_GAIN
        try:
            L.VOICE_GAIN = 0.5
            assert L.ambience_mix("gym", 0.05) == pred
        finally:
            L.VOICE_GAIN = povodne


class TestNikdyDvakratRovnako:
    """Séria hlasoviek s rovnakým tichom, hlasitosťou a tempom znie ako stroj."""

    def test_ticho_na_okrajoch_je_v_rozsahu(self):
        import random
        import livevoice as L

        r = random.Random(1)
        for _ in range(50):
            lead, tail = L.lead_tail(r)
            assert L.LEAD_MIN <= lead <= L.LEAD_MAX
            assert L.TAIL_MIN <= tail <= L.TAIL_MAX

    def test_ticho_nie_je_zakazdym_rovnake(self):
        import random
        import livevoice as L

        r = random.Random(7)
        vzorky = {L.lead_tail(r) for _ in range(20)}
        assert len(vzorky) > 15, "okraje musia kolísať"

    def test_hlasitost_hlasovky_kolise_v_nastavenom_rozsahu(self):
        """Rozsah je polovičný oproti prvej verzii — bolo to prehnane hlasné."""
        import random
        import livevoice as L

        r = random.Random(3)
        hodnoty = [L.note_volume(r) for _ in range(60)]
        assert all(L.NOTE_MIN <= v <= L.NOTE_MAX for v in hodnoty)
        assert L.NOTE_MAX <= 0.45, "hlasnejšie už bolo priveľa"
        assert len(set(hodnoty)) > 40, "hlasitosť sa musí meniť"

    def test_tempo_je_vacsinou_rychlejsie(self):
        import random
        import livevoice as L

        r = random.Random(11)
        vzorky = [L.wobble_tempo(1.12, r) for _ in range(400)]
        rychlejsie = sum(1 for t in vzorky if t > 1.12)
        assert 0.6 < rychlejsie / len(vzorky) < 0.85, "väčšinou, ale nie vždy"
        assert min(vzorky) >= 1.12 - L.TEMPO_DOWN - 0.001
        assert max(vzorky) <= 1.12 + L.TEMPO_UP + 0.001

    def test_tempo_ostane_v_medziach_atempo(self):
        import livevoice as L

        assert 0.5 <= L.wobble_tempo(0.5) <= 2.0
        assert 0.5 <= L.wobble_tempo(3.0) <= 2.0

    def test_ticho_ide_az_za_tempo(self):
        """Keby šlo pred atempo, skrátilo by sa spolu s rečou."""
        import livevoice as L

        mic, _, _, _ = L._chain("real", 1.2)
        assert "atempo" in mic and "adelay" not in mic

    def test_hlasitost_hlasovky_sa_dostane_do_retazca(self):
        import livevoice as L

        _, chain, _, _ = L._chain("real", 1.12, volume=0.55)
        assert "0.550" in chain


class TestVPostelisaNebucha:
    def test_spalna_je_najtichsia_z_miestnosti(self):
        import livevoice as L

        spalna = L.ambience_mix("bedroom", 0.05)[0]
        ostatne = [
            L.ambience_mix(m, 0.05)[0]
            for m in ("home", "kitchen", "car", "outside", "cafe", "gym")
        ]
        assert spalna < min(ostatne)

    def test_ulica_je_najvyraznejsia(self):
        import livevoice as L

        ulica = L.ambience_mix("outside", 0.05)[0]
        ostatne = [
            L.ambience_mix(m, 0.05)[0]
            for m in ("home", "bedroom", "kitchen", "car", "cafe", "gym")
        ]
        assert ulica > max(ostatne)


class TestTempoPriNahravani:
    """Zrýchľovať hotový hlas cez atempo ho znehodnocuje.

    Odmerané na tej istej vete: v3 bez `speed` 8,32 s, so `speed` 1.15 dokonca
    10,48 s — čísla nedávajú zmysel, v3 ho ignoruje. v2 na tom istom mieste
    9,06 s bez a 6,04 s so `speed`. Preto sa tempo pýta priamo pri nahrávaní
    a atempo ostáva len pre model, ktorý nepočúva.
    """

    def test_atempo_odpadne_ked_model_speed_poslucha(self, monkeypatch):
        import asyncio
        import eleven
        import livevoice as L

        zachytene = {}

        async def fake_speech(text, key, voice, speed=None):
            zachytene["speed"] = speed
            return b"MP3", eleven.FALLBACK_MODEL_ID   # v2 speed poslúcha

        async def fake_mix(voice, amb, level, strength, tempo, name, **kw):
            zachytene["atempo"] = tempo
            return b"OGG"

        monkeypatch.setattr(eleven, "speech", fake_speech)
        monkeypatch.setattr(eleven, "ambience", lambda *a, **k: _none())
        monkeypatch.setattr(L, "_mix", fake_mix)
        asyncio.run(L.speak("nieco dlhsie na povedanie", "k", "v", "none", "real"))

        assert zachytene["speed"] > 0.9, "tempo sa musí vypýtať pri nahrávaní"
        assert zachytene["atempo"] == 1.0, "atempo sa už nesmie použiť"

    def test_atempo_zaskoci_ked_model_speed_ignoruje(self, monkeypatch):
        import asyncio
        import eleven
        import livevoice as L

        zachytene = {}

        async def fake_speech(text, key, voice, speed=None):
            return b"MP3", eleven.MODEL_ID           # v3 speed ignoruje

        async def fake_mix(voice, amb, level, strength, tempo, name, **kw):
            zachytene["atempo"] = tempo
            return b"OGG"

        monkeypatch.setattr(eleven, "speech", fake_speech)
        monkeypatch.setattr(eleven, "ambience", lambda *a, **k: _none())
        monkeypatch.setattr(L, "_mix", fake_mix)
        asyncio.run(L.speak("nieco dlhsie na povedanie", "k", "v", "none", "real"))

        assert zachytene["atempo"] != 1.0, "inak by hovorila pomaly"

    def test_speed_sa_posiela_len_modelu_ktory_ho_poslucha(self):
        import eleven

        assert eleven.FALLBACK_MODEL_ID in eleven.HONOURS_SPEED
        assert eleven.MODEL_ID not in eleven.HONOURS_SPEED


async def _none():
    return None


class TestHlasovkaJeKratka:
    """Nikto do telefónu nenahovorí odsek."""

    def test_dve_vety_prejdu(self):
        import livevoice as L

        assert L.worth_speaking(
            "like fifteen more minutes then im out, my legs are toast. "
            "gonna crawl home after this"
        )

    def test_cely_odsek_neprejde(self):
        import livevoice as L

        dlhe = (
            "ugh it was one of those days where nothing big happened but i still "
            "feel wiped. woke up late, went to the gym for a bit, then just drove "
            "around taking some photos cause the light was nice. came home, made "
            "food, scrolled on my phone way too long."
        )
        assert not L.worth_speaking(dlhe), "toto patrí do textu, nie do hlasovky"

    def test_jedno_slovo_tiez_neprejde(self):
        import livevoice as L

        assert not L.worth_speaking("ok")

    def test_prompt_hovori_o_dlzke(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 9, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, can_speak=True,
        )
        assert "JEDNA veta" in out


class TestHlasovkouSaNezacina:
    """Cudzí človek, ktorý hneď dostane nahrávku, dostane skôr podozrenie.

    Naživo to vyzeralo takto: prvá správa bola „👋" a odpoveď odišla ako
    hlasovka so slovami „hey stranger, was wondering when ud pop up again".
    """

    def test_prompt_zakazuje_hlasovku_na_zaciatku(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 9, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, can_speak=True,
        )
        assert "NIKDY ako prvú správu" in out

    def test_pri_pochybnosti_ma_byt_drza_nie_obhajoba(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 9, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, can_speak=True,
        )
        assert "KEĎ NEVERÍ" in out and "DRZÁ" in out


class TestPrvaSpravaNieJeZnovunadviazanie:
    """`gap is None` je prvá správa v živote, nie dlhá pauza.

    Kým sa to nerozlišovalo, model dostal pokyn „prešlo dosť času, môžeš
    hodiť, že si sa dlho neozvala" — na úplne prvý pozdrav od cudzieho.
    """

    @staticmethod
    def _prompt(gap):
        from persona import build_system_prompt
        from datetime import datetime

        return build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 1, "funnel_stage": "cold"},
            allow_link=False, asked_if_ai=False, gap=gap,
            now_local=datetime(2026, 8, 17, 20, 0),
        )

    def test_prva_sprava_zakazuje_hey_stranger(self):
        out = self._prompt(None)
        assert "ÚPLNE PRVÁ správa" in out
        assert "hey stranger" in out, "musí to vymenovať ako zakázané"
        assert "Prešlo dosť času" not in out

    def test_po_dlhej_pauze_sa_nadviazat_smie(self):
        out = self._prompt(40.0)
        assert "Prešlo dosť času" in out
        assert "ÚPLNE PRVÁ správa" not in out


class TestMazanieKonverzacie:
    """„Skús od znova" musí naozaj znamenať od nuly.

    Kým sa mazali len správy, ostávali po nich fakty, epizódy, sľuby aj
    tvrdenia — takže „úplne nový človek" si po prvej správe pamätal, čím sa
    živí. Na jednom testovacom účte tak zostalo 11 tvrdení pri 0 správach.
    """

    def test_zmaze_aj_pamat_nielen_spravy(self):
        import asyncio
        import db as D
        import transport as T

        zmazane = []

        class FakeClient:
            def __init__(self):
                self.base_url = "https://x/rest/v1"

            async def delete(self, path, params=None):
                zmazane.append(path)
                return _Odpoved()

            async def get(self, path, params=None, headers=None):
                return _Odpoved(json_data=[])

            async def patch(self, path, params=None, json=None, headers=None):
                self.patched = json
                return _Odpoved()

        class _Odpoved:
            def __init__(self, json_data=None):
                self._j = json_data if json_data is not None else []
                self.content = b"[]"
                self.headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return self._j

        # V Telepipe spojenie drží transport, nie Db — klienta podvrhneme jemu.
        prenos = T.SupabaseTransport.__new__(T.SupabaseTransport)
        prenos._client = FakeClient()
        baza = D.TenantDb(prenos, "test-model")
        asyncio.run(baza.wipe_conversation(1))

        for tabulka in (D.MESSAGES, D.FACTS, D.EPISODES, D.LOOPS, D.CLAIMS,
                        D.PHOTO_SENDS, D.VOICE_SENDS):
            assert tabulka in zmazane, f"{tabulka} sa nezmazala"

    def test_vynuluje_aj_meno_a_register_tem(self):
        import asyncio
        import db as D
        import transport as T

        class FakeClient:
            def __init__(self):
                self.base_url = "https://x/rest/v1"
                self.patched = None

            async def delete(self, path, params=None):
                return _O()

            async def get(self, path, params=None, headers=None):
                return _O([])

            async def patch(self, path, params=None, json=None, headers=None):
                self.patched = json
                return _O()

        class _O:
            def __init__(self, j=None):
                self._j = j if j is not None else []
                self.content = b"[]"
                self.headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return self._j

        # V Telepipe spojenie drží transport, nie Db — klienta podvrhneme jemu.
        prenos = T.SupabaseTransport.__new__(T.SupabaseTransport)
        prenos._client = FakeClient()
        baza = D.TenantDb(prenos, "test-model")
        asyncio.run(baza.wipe_conversation(1))
        patch = baza._client.patched
        assert patch["partner_name"] == ""
        assert patch["asked_topics"] == {}
        assert patch["msg_count"] == 0


class TestKolisanieHlasitosti:
    """Aj pravidelná sínusovka je vzor. Skutočná hlasovka má nepravidelnosti."""

    def test_kratka_nahravka_ma_par_udalosti(self):
        import random
        import livevoice as L

        for seed in range(30):
            ud = L.volume_events(7.0, lead=0.9, rng=random.Random(seed))
            assert 1 <= len(ud) <= L.EVENTS_MAX + 1, f"seed {seed}: {len(ud)}"

    def test_udalosti_padnu_do_reci_nie_do_ticha(self):
        import random
        import livevoice as L

        lead, dlzka = 0.9, 6.0
        for seed in range(30):
            for kedy, _, _ in L.volume_events(dlzka, lead, random.Random(seed)):
                assert lead < kedy < lead + dlzka

    def test_udalosti_sa_neprekryvaju(self):
        import random
        import livevoice as L

        for seed in range(50):
            ud = L.volume_events(9.0, 0.9, random.Random(seed))
            for (t1, _, w1), (t2, _, w2) in zip(ud, ud[1:]):
                assert abs(t2 - t1) >= (w1 + w2) * 2 - 0.01

    def test_zadrh_je_vzacny(self):
        """Raz za veľa hlasoviek, nie v každej tretej."""
        import random
        import livevoice as L

        r = random.Random(1)
        so_zadrhom = 0
        for _ in range(600):
            ud = L.volume_events(7.0, 0.9, r)
            if any(h >= L.GLITCH_DEPTH[0] for _, h, _ in ud):
                so_zadrhom += 1
        podiel = so_zadrhom / 600
        assert 0.01 < podiel < 0.12, f"zádrh v {podiel:.0%} nahrávok"

    def test_kolisanie_musi_byt_pocut(self):
        """Jemné kolísanie o pár percent sa stratí pod kompresorom.

        Prvá verzia mala poklesy 7–18 % a v nahrávke ich nebolo počuť —
        z kolísania bola zase plochá čiara. Skutočná zmena je, keď hlas zíde
        na necelú polovicu a vráti sa.
        """
        import random
        import livevoice as L

        r = random.Random(2)
        hlbky = [h for _ in range(300) for _, h, _ in L.volume_events(7.0, 0.9, r)]
        assert min(hlbky) >= 0.20, "plytší pokles je pod kompresorom neviditeľný"
        vyrazne = sum(1 for h in hlbky if h >= 0.30)
        assert vyrazne / len(hlbky) > 0.5, "väčšina zmien musí byť naozaj počuť"

    def test_prechod_trva_sekundu_az_tri(self):
        import random
        import livevoice as L

        r = random.Random(5)
        sirky = [w for _ in range(300) for _, h, w in L.volume_events(9.0, 0.9, r)
                 if h < L.GLITCH_DEPTH[0]]
        # Zvon je „viditeľný" zhruba na 1.5 šírky, takže prechod trvá ~1–3 s.
        prechody = [w * 1.5 for w in sirky]
        assert min(prechody) < 1.2, "musia byť aj rýchle zmeny"
        assert max(prechody) > 2.2, "aj pomalé, ktoré trvajú pár sekúnd"

    def test_velmi_kratka_nahravka_nema_udalosti(self):
        import livevoice as L

        assert L.volume_events(1.0) == []

    def test_vyraz_sa_neprepadne_do_minusu(self):
        import livevoice as L

        # Dva hlboké poklesy na tom istom mieste — poistka to musí podchytiť.
        vyraz = L.volume_expression([(2.0, 0.9, 0.1), (2.0, 0.9, 0.1)])
        assert vyraz.startswith("max(0.02")

    def test_vyraz_prejde_cez_ffmpeg(self):
        """Najrizikovejšie miesto: escapovanie čiarok vo filtergrafe."""
        import random
        import subprocess
        import livevoice as L

        vyraz = L.volume_expression(L.volume_events(7.0, 0.9, random.Random(3)))
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=3",
             "-filter_complex", f"[0:a]volume='{vyraz}':eval=frame,anull[o]",
             "-map", "[o]", "-f", "null", "-"],
            capture_output=True,
        )
        assert out.returncode == 0, out.stderr.decode()[:300]


class TestTestovaciUcet:
    """„Píš mi len hlasovky" musí znamenať len hlasovky."""

    def test_dlha_odpoved_sa_este_da_nahovorit(self):
        import livevoice as L

        dlhe = "a" * 200
        assert not L.worth_speaking(dlhe), "bežne je to na hlasovku priveľa"
        assert L.worth_speaking(dlhe, L.TEST_MIN_CHARS, L.TEST_MAX_CHARS)

    def test_kratka_odpoved_sa_tiez_nahovori(self):
        import livevoice as L

        assert not L.worth_speaking("heyy")
        assert L.worth_speaking("heyy", L.TEST_MIN_CHARS, L.TEST_MAX_CHARS)

    def test_odkaz_sa_nenahovori_ani_testovaciemu(self):
        import livevoice as L

        assert not L.worth_speaking(
            "tu mas https://fanvue.com/x a este nieco navyse",
            L.TEST_MIN_CHARS, L.TEST_MAX_CHARS,
        )


class TestMazanieNestiahneStaruHistoriu:
    """Telegram si históriu drží aj po vymazaní našej.

    Keď sa `last_msg_id` vynuluje, Reconciler stiahne späť posledných tridsať
    správ a odpovie na ne, akoby prišli teraz. Naživo tak po vyčistení chatu
    dorazilo dvanásť starých správ naraz a vyzeralo to, že píše sama od seba.
    """

    def test_wipe_nechava_last_msg_id_na_pokoji(self):
        import asyncio
        import db as D
        import transport as T

        class _O:
            def __init__(self, j=None):
                self._j = j if j is not None else []
                self.content = b"[]"
                self.headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return self._j

        class FakeClient:
            def __init__(self):
                self.base_url = "https://x/rest/v1"
                self.patched = None

            async def delete(self, path, params=None):
                return _O()

            async def get(self, path, params=None, headers=None):
                return _O([])

            async def patch(self, path, params=None, json=None, headers=None):
                self.patched = json
                return _O()

        # V Telepipe spojenie drží transport, nie Db — klienta podvrhneme jemu.
        prenos = T.SupabaseTransport.__new__(T.SupabaseTransport)
        prenos._client = FakeClient()
        baza = D.TenantDb(prenos, "test-model")
        asyncio.run(baza.wipe_conversation(1))
        assert "last_msg_id" not in baza._client.patched


class TestKoniecHlasovky:
    """Po dohovorení ostane chvíľa ticha a miestnosť sa stratí."""

    def test_koniec_je_dlhsi_nez_zaciatok(self):
        import livevoice as L

        assert L.TAIL_MAX > L.LEAD_MAX
        assert L.TAIL_MIN >= 1.0, "kratší koniec vyzerá ako odseknutá nahrávka"
        assert L.TAIL_MAX <= 3.0

    def test_chvost_kolise_v_rozsahu(self):
        import random
        import livevoice as L

        r = random.Random(9)
        chvosty = [L.lead_tail(r)[1] for _ in range(60)]
        assert all(L.TAIL_MIN <= t <= L.TAIL_MAX for t in chvosty)
        assert len(set(chvosty)) > 40, "dĺžka ticha musí kolísať"


class TestPozadieNieJeZakazdymRovnake:
    """Nastavená hlasitosť miestnosti je strop, nie pevná hodnota."""

    def test_nasobic_je_v_rozsahu(self):
        import random
        import livevoice as L

        r = random.Random(6)
        hodnoty = [L.ambience_jitter(r) for _ in range(80)]
        assert all(L.AMBIENCE_JITTER_MIN <= v <= L.AMBIENCE_JITTER_MAX for v in hodnoty)

    def test_nikdy_hlasnejsie_nez_nastavenie(self):
        import random
        import livevoice as L

        r = random.Random(8)
        assert max(L.ambience_jitter(r) for _ in range(200)) <= 1.0, (
            "posuvník v dashboarde je strop — nad neho sa ísť nesmie"
        )

    def test_hlasitost_sa_naozaj_mení(self):
        import random
        import livevoice as L

        r = random.Random(4)
        hodnoty = {L.ambience_jitter(r) for _ in range(40)}
        assert len(hodnoty) > 30

    def test_miestnosti_si_drzia_vzajomny_pomer(self):
        """Jitter mení hladinu, nie charakter — ulica ostáva hlasnejšia."""
        import livevoice as L

        for nasobic in (0.6, 0.8, 1.0):
            ulica = L.ambience_mix("outside", 0.05 * nasobic)[0]
            spalna = L.ambience_mix("bedroom", 0.05 * nasobic)[0]
            assert ulica > spalna
