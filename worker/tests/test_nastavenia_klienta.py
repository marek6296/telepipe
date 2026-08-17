"""Nastavenia z dashboardu naozaj menia správanie.

Nie „stĺpec sa niekde číta“, ale „iná hodnota = iný výsledok“. Každý test je
jedno políčko z karty Persona / Behavior / Voice (a pár z Fanvue) a drží ten
istý kontrakt, aký sľubuje popis pod ním v UI. Keď sa v predlohe zmení význam
nastavenia, padne to sem — a nie až u klienta.

Pozn.: `build_system_prompt` skladá slovenský prompt, preto sú aj kotvy
v testoch slovenské. Hodnoty, ktoré zadáva klient, sú naopak jeho vlastné
a hľadáme ich doslovne.
"""
import random

import behavior as bhv
import limity
import livevoice
import speech
from behavior import Behavior
from persona import build_system_prompt

# Persona so VŠETKÝMI políčkami karty Persona, každé s nezameniteľnou hodnotou.
PERSONA = {
    "name": "Klaudia",
    "age": 24,
    "city": "Lisabon",
    "language": "ODPOVEDAJ-PO-ANGLICKY-MARKER",
    "languages": "JAZYKY-MARKER slovensky a nemecky",
    "backstory": "BACKSTORY-MARKER studuje dizajn",
    "tone": "TONE-MARKER hravy a drzy",
    "msg_style": "STYLE-MARKER kratke vety",
    "boundaries": "HRANICE-MARKER nikdy nesluby stretnutie",
    "funnel_rules": "FUNNEL-MARKER najprv sa spoznajte",
    "cta_link": "https://fanvue.com/klaudia-marker",
    "extra_rules": "EXTRA-MARKER piatok je den fotenia",
    "examples": "EXAMPLES-MARKER heyy co robis",
}

USER = {"tg_id": 42, "msg_count": 8, "funnel_stage": "warm"}


def prompt(persona=None, behavior=None, **kwargs):
    """System prompt s rozumnými východiskami — testy menia len to svoje."""
    args = {
        "allow_link": False,
        "asked_if_ai": False,
        "behavior": behavior or Behavior(),
    }
    args.update(kwargs)
    return build_system_prompt(persona or PERSONA, dict(USER), **args)


# --------------------------------------------------------------------------- #
#  Karta PERSONA — každé políčko sa musí dostať do promptu                     #
# --------------------------------------------------------------------------- #

class TestPersonaVPrompte:
    """Čo klient napíše do Persony, to musí model naozaj vidieť.

    Toto je celá hodnota tej karty: políčko, ktoré sa do promptu nedostane, je
    políčko, ktoré klientovi klame.
    """

    def test_vsetky_policka_su_v_prompte(self):
        out = prompt(allow_link=True)
        chyba = [
            f"{pole}={hodnota!r}"
            for pole, hodnota in PERSONA.items()
            if str(hodnota) not in out
        ]
        assert not chyba, f"Persona sa nedostala do promptu: {chyba}"

    def test_kazde_policko_ma_svoju_sekciu(self):
        """Hodnota nesmie len tak visieť — patrí pod nadpis, ktorý jej dá význam."""
        out = prompt(allow_link=True)
        for nadpis, marker in (
            ("JAZYK ODPOVEDÍ", "ODPOVEDAJ-PO-ANGLICKY-MARKER"),
            ("ČO OVLÁDAŠ ZA JAZYKY", "JAZYKY-MARKER"),
            ("O TEBE", "BACKSTORY-MARKER"),
            ("TÓN", "TONE-MARKER"),
            ("ŠTÝL SPRÁV", "STYLE-MARKER"),
            ("HRANICE", "HRANICE-MARKER"),
            ("ĎALŠIE POKYNY", "EXTRA-MARKER"),
            ("AKO NAVIESŤ NA OBSAH", "FUNNEL-MARKER"),
            ("TAKTO PÍŠEŠ TY", "EXAMPLES-MARKER"),
        ):
            assert nadpis in out, f"chýba sekcia {nadpis}"
            useknute = out[out.index(nadpis):]
            assert marker in useknute[:600], f"{marker} nie je pod nadpisom {nadpis}"

    def test_meno_vek_mesto_su_prva_veta(self):
        out = prompt()
        assert out.startswith("Si Klaudia.")
        assert "Máš 24 rokov." in out and "Žiješ v Lisabon." in out

    def test_prazdna_persona_nevyrobi_prazdne_sekcie(self):
        """Kto nevyplní tón, nemá dostať nadpis TÓN s ničím pod ním."""
        out = prompt({"name": "Klaudia"})
        assert "TÓN\n" not in out and "O TEBE" not in out
        assert "ČO OVLÁDAŠ ZA JAZYKY" not in out

    def test_bez_veku_a_mesta_sa_nic_nevymysli(self):
        out = prompt({"name": "Klaudia"})
        assert "rokov" not in out.split("\n")[0]
        assert "Žiješ v" not in out


class TestOdkazKlienta:
    """`cta_link` je JEDINÝ odkaz, ktorý smie odísť."""

    def test_povoleny_odkaz_je_ten_z_persony(self):
        out = prompt(allow_link=True)
        assert "ODKAZ JE TERAZ POVOLENÝ" in out
        assert "https://fanvue.com/klaudia-marker" in out

    def test_odkaz_si_nesie_koho_sa_tyka(self):
        """Bez atribúcie sa fanúšik na Fanvue nedá spojiť s chatom."""
        out = prompt(allow_link=True)
        assert "client_reference_id=" in out

    def test_zakazany_odkaz_sa_v_prompte_neobjavi(self):
        out = prompt(allow_link=False)
        assert "ODKAZ JE TERAZ ZAKÁZANÝ" in out
        assert "fanvue.com/klaudia-marker" not in out

    def test_prazdny_odkaz_znamena_ziadny_odkaz(self):
        """UI sľubuje: „Leave this empty and she never sends a link at all.“"""
        bez = dict(PERSONA, cta_link="")
        out = prompt(bez, allow_link=True)
        assert "ODKAZ JE TERAZ POVOLENÝ" not in out


# --------------------------------------------------------------------------- #
#  Karta BEHAVIOR — význam prepínačov podľa predlohy                           #
# --------------------------------------------------------------------------- #

class TestStylChatu:
    def test_mode_real_nikdy_neprizna_ai(self):
        out = prompt(behavior=Behavior(mode="real"))
        assert "Si skutočné dievča, nie program." in out
        assert "Si AI postava a netajíš to." not in out

    def test_mode_ai_to_prizna(self):
        out = prompt(behavior=Behavior(mode="ai"))
        assert "Si AI postava a netajíš to." in out

    def test_kazda_uroven_pikantnosti_da_ine_pravidlo(self):
        pravidla = {h: prompt(behavior=Behavior(heat=h)) for h in ("mild", "medium", "hot")}
        assert "slušná" in pravidla["mild"]
        assert "surové opisy" in pravidla["medium"]
        assert "veľmi otvorená a trúfalá" in pravidla["hot"]
        # Tri rôzne nastavenia nesmú vyrobiť tri rovnaké prompty.
        assert len({p for p in pravidla.values()}) == 3

    def test_kazda_uroven_slangu_da_ine_pravidlo(self):
        out_none = prompt(behavior=Behavior(slang="none"))
        out_light = prompt(behavior=Behavior(slang="light"))
        out_medium = prompt(behavior=Behavior(slang="medium"))
        assert "Žiadny chatový slang" in out_none
        assert "VEĽMI striedmo" in out_light
        assert "Píš ležérne" in out_medium

    def test_slang_none_prepise_tvrde_skratky_aj_v_texte(self):
        """Nie je to len pokyn do promptu — text sa po generovaní ešte upraví."""
        import humanize
        assert humanize.soften_slang("ngl u r cute", "none") != "ngl u r cute"
        assert humanize.soften_slang("ngl u r cute", "medium") == "ngl u r cute"

    def test_bez_diakritiky_prida_pokyn(self):
        assert "DIAKRITIKA" in prompt(behavior=Behavior(no_diacritics=True))
        assert "DIAKRITIKA" not in prompt(behavior=Behavior(no_diacritics=False))


class TestVlnyAktivity:
    """„Waves of activity“ — vypnuté znamená rovnomerné tempo, nie pomalšie."""

    def test_vypnute_vlny_nezrychluju_ani_nespomaluju(self):
        from datetime import datetime
        teraz = datetime(2026, 5, 5, 14, 0)
        assert bhv.wave_factor(Behavior(activity_waves=False), teraz) == 1.0

    def test_zapnute_vlny_menia_tempo(self):
        from datetime import datetime
        faktory = {
            bhv.wave_factor(Behavior(activity_waves=True), datetime(2026, 5, 5, h, 0))
            for h in range(24)
        }
        assert len(faktory) > 1, "vlny musia byť medzi hodinami cítiť"


class TestAktivneOkno:
    def test_rovnaky_zaciatok_a_koniec_je_nonstop(self):
        """UI sľubuje: „Set both to the same time and she answers around the clock.“"""
        from datetime import datetime
        assert bhv.in_active_window(datetime(2026, 5, 5, 3, 0), 600, 600)

    def test_okno_smie_prejst_cez_polnoc(self):
        """UI sľubuje: „12:12 to 02:30 is a normal night owl.“"""
        from datetime import datetime
        start, end = 12 * 60 + 12, 2 * 60 + 30
        assert bhv.in_active_window(datetime(2026, 5, 5, 23, 0), start, end)
        assert bhv.in_active_window(datetime(2026, 5, 5, 1, 0), start, end)
        assert not bhv.in_active_window(datetime(2026, 5, 5, 8, 0), start, end)


class TestPozdravenie:
    """`greeting_gap_hours` — pod touto medzerou sa nezdraví."""

    def test_kratka_medzera_zakaze_pozdrav(self):
        out = prompt(behavior=Behavior(greeting_gap_hours=6), gap=1.0)
        assert "NEZDRAV SA" in out

    def test_dlha_medzera_pozdrav_povoli(self):
        out = prompt(behavior=Behavior(greeting_gap_hours=6), gap=9.0)
        assert "NEZDRAV SA" not in out

    def test_nastavenie_posuva_hranicu(self):
        """Rovnaká medzera, iné nastavenie, iný výsledok — to je celý zmysel poľa."""
        assert bhv.greeting_allowed(Behavior(greeting_gap_hours=2), 3.0)
        assert not bhv.greeting_allowed(Behavior(greeting_gap_hours=24), 3.0)


class TestBezpecnostneStropy:
    """Tri stropy z karty Behavior („Looking like one person“).

    Worker ich čítal od začiatku, do dashboardu pribudli až teraz — takže tu
    stojí presne to, čo o nich sľubuje popis pod políčkom.
    """

    def test_max_active_chats_odlozi_noveho_cloveka(self):
        aktivni = {1, 2, 3}
        assert not limity.ma_miesto(99, aktivni, 3)
        assert limity.ma_miesto(99, aktivni, 5)

    def test_kto_uz_miesto_drzi_prejde_vzdy(self):
        """Rozhovor sa nesmie preseknúť v polovici, keď medzitým napíše niekto ďalší."""
        assert limity.ma_miesto(2, {1, 2, 3}, 3)

    def test_nula_vypina_strop_rozhovorov(self):
        """UI sľubuje: „0 turns the limit off.“"""
        assert limity.ma_miesto(99, {1, 2, 3, 4, 5}, 0)

    def test_max_outreach_brzdi_len_nove_oslovenie(self):
        oslovenych = {1, 2}
        assert not limity.smie_oslovit(99, oslovenych, 2)
        assert limity.smie_oslovit(99, oslovenych, 5)

    def test_odpoved_tomu_kto_uz_pisal_strop_neriesi(self):
        """UI sľubuje: „Replies do not count.“"""
        assert limity.smie_oslovit(1, {1, 2}, 2)

    def test_nula_vypina_strop_oslovovania(self):
        assert limity.smie_oslovit(99, {1, 2, 3}, 0)

    def test_stropy_su_v_dataclass_a_prezijú_from_row(self):
        """Keby pole v dataclass chýbalo, `from_row` ho ticho zahodí."""
        b = Behavior.from_row(
            {"max_active_chats": 9, "chat_slot_min": 120, "max_outreach_per_hour": 12}
        )
        assert (b.max_active_chats, b.chat_slot_min, b.max_outreach_per_hour) == (9, 120, 12)


class TestRozsahyZDashboardu:
    """Čo UI pustí, to `Behavior.from_row` musí prežiť bez výnimky."""

    def test_krajne_hodnoty_formulara_prejdu(self):
        b = Behavior.from_row({
            "active_start_min": 1439, "active_end_min": 0,
            "debounce_min_s": 0, "debounce_max_s": 600,
            "read_delay_min_s": 0, "read_delay_max_s": 3600,
            "reply_delay_min_s": 0, "reply_delay_max_s": 3600,
            "quick_reply_chance": 1, "seen_only_chance": 0,
            "long_pause_chance": 1, "defer_reply_chance": 1,
            "defer_min_s": 172800, "defer_max_s": 172800,
            "question_chance": 1, "gag_chance": 0,
            "greeting_gap_hours": 168, "summary_every": 1,
            "max_replies_per_hour": 500, "max_links_per_hour": 0,
            "photo_cooldown_min": 1440, "morning_max_per_day": 500,
            "voice_chance": 1, "voice_tempo": 2.0, "voice_ambience_level": 1,
        })
        assert b.defer_max_s == 172800 and b.voice_tempo == 2.0

    def test_prevratene_rozpatie_nespadne(self):
        """Klient smie omylom dať min > max; z toho nesmie byť výnimka."""
        b = Behavior(reply_delay_min_s=100, reply_delay_max_s=10)
        assert 10 <= bhv.reply_delay(b, random.Random(1)) <= 100

    def test_nulova_sanca_znamena_nikdy(self):
        vypnute = Behavior(
            seen_only_chance=0, long_pause_chance=0, defer_reply_chance=0,
            quick_reply_chance=0,
        )
        r = random.Random(7)
        assert bhv.seen_only_delay(vypnute, r) == 0.0
        assert bhv.long_pause_delay(vypnute, r) == 0.0
        assert bhv.should_defer_reply(vypnute, 5, "ahoj", r) == 0.0
        assert bhv.quick_reply(vypnute, "ahoj", r) is None

    def test_plna_sanca_znamena_vzdy(self):
        vzdy = Behavior(seen_only_chance=1.0, seen_only_min_s=10, seen_only_max_s=20)
        assert bhv.seen_only_delay(vzdy, random.Random(3)) > 0


# --------------------------------------------------------------------------- #
#  Karta VOICE                                                                 #
# --------------------------------------------------------------------------- #

class TestHlasovky:
    def test_voice_chance_nula_nikdy_neposle(self):
        veta = "hey there, i was just thinking about you today"
        assert not any(
            livevoice.should_speak(veta, random.Random(i), chance=0.0)
            for i in range(50)
        )

    def test_voice_chance_jedna_posle_vzdy(self):
        veta = "hey there, i was just thinking about you today"
        assert all(
            livevoice.should_speak(veta, random.Random(i), chance=1.0)
            for i in range(50)
        )

    def test_kazda_vynimka_sa_da_vypnut_zvlast(self):
        """Šesť prepínačov z „Moments worth her voice“ — každý sám za seba."""
        situacie = {
            "asked_for_voice": "voice_when_asked",
            "doubts_her": "voice_when_doubted",
            "he_voiced": "voice_when_he_voices",
            "away": "voice_when_away",
            "winding_down": "voice_on_goodnight",
            "hot_stuck": "voice_when_hot",
        }
        for situacia, prepinac in situacie.items():
            zapnuty = Behavior(**{prepinac: True})
            vypnuty = Behavior(**{prepinac: False})
            assert speech.exception_reason(zapnuty, **{situacia: True}), (
                f"{prepinac}=True mal hlasovku pustiť"
            )
            assert not speech.exception_reason(vypnuty, **{situacia: True}), (
                f"{prepinac}=False mal hlasovku zastaviť"
            )

    def test_ziadna_situacia_ziadna_vynimka(self):
        assert speech.exception_reason(Behavior()) == ""

    def test_vsetky_miestnosti_z_ui_maju_zvuk_aj_mix(self):
        """Výber v UI, prompt pre ElevenLabs a mix musia poznať tie isté miestnosti."""
        import eleven
        z_ui = set(bhv.AMBIENCE_CYCLE)
        assert z_ui == set(eleven.AMBIENCES), "ponuka v UI a zvuky sa rozišli"
        for miestnost in z_ui:
            hlasitost, dolna, horna = livevoice.ambience_mix(miestnost, 0.5)
            assert dolna < horna, f"{miestnost} nemá zmysluplný filter"

    def test_ticho_naozaj_mlci(self):
        assert livevoice.ambience_mix("none", 1.0)[0] == 0.0

    def test_miestnosti_znejú_odlisne(self):
        hlasitosti = {
            livevoice.ambience_mix(m, 0.5)[0] for m in bhv.AMBIENCE_CYCLE if m != "none"
        }
        assert len(hlasitosti) > 1, "všetky miestnosti mixujú rovnako"

    def test_hlasitost_pozadia_sa_prejavi(self):
        ticho = livevoice.ambience_mix("home", 0.0)[0]
        hlasno = livevoice.ambience_mix("home", 1.0)[0]
        assert ticho == 0.0 and hlasno > ticho

    def test_vsetky_kvality_nahravky_z_ui_maju_recept(self):
        for sila in bhv.STRENGTH_CYCLE:
            mic, chain, hiss, bitrate = livevoice._chain(sila, 1.12, 1.0, 30)
            assert "atempo" in mic and bitrate

    def test_kvality_sa_navzajom_lisia(self):
        bitrate = {livevoice._chain(s, 1.12, 1.0, 30)[3] for s in bhv.STRENGTH_CYCLE}
        assert len(bitrate) == len(bhv.STRENGTH_CYCLE)

    def test_tempo_z_dashboardu_ide_do_mixu(self):
        pomaly = livevoice._chain("real", 0.5, 1.0, 30)[0]
        rychlo = livevoice._chain("real", 2.0, 1.0, 30)[0]
        assert "atempo=0.500" in pomaly and "atempo=2.000" in rychlo

    def test_krajne_tempo_zo_slidera_ffmpeg_znesie(self):
        """Slider púšťa 0.5–2.0 a presne toľko `atempo` zvláda jedným filtrom."""
        for tempo in (0.5, 1.0, 1.12, 2.0):
            for _ in range(20):
                assert 0.5 <= livevoice.wobble_tempo(tempo, random.Random()) <= 2.0

    def test_model_nesmie_tempo_pretlacit_mimo_rozumu(self):
        """Pokyn z modelu sa berie len v rozumnom pásme, inak platí nastavenie."""
        assert speech.tempo_from({"tempo": "9.0"}, 1.12) == 1.12
        assert speech.tempo_from({"tempo": "1.30"}, 1.12) == 1.30
