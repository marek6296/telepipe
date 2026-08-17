"""Fotky — len na vyžiadanie, nikdy tá istá dvakrát, správnej modelke."""
import asyncio
import random
from datetime import datetime, timedelta, timezone

import photos as P
import userbot
import pytest

from test_reply_flow import build, user_row

pytestmark = pytest.mark.usefixtures("fast")

RNG = random.Random(3)
NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}

LIB = [
    {"id": 1, "caption": "selfie v posteli", "situation": "leží v posteli",
     "parts": ["vecer", "noc"], "spicy": True, "active": True},
    {"id": 2, "caption": "selfie v meste", "situation": "vonku na nákupoch",
     "parts": ["poobede"], "spicy": False, "active": True},
    {"id": 3, "caption": "selfie na gauči", "situation": "doma na gauči",
     "parts": [], "spicy": False, "active": True},
]


class TestWantsPhoto:
    @pytest.mark.parametrize(
        "text",
        [
            "send me a pic",
            "can i see you",
            "any pics?",
            "what are you wearing",
            "send nudes",
            "show me what you doing",
            "selfie?",
            "let me see u",
        ],
    )
    def test_recognises_a_request(self, text):
        assert P.wants_photo(text)

    @pytest.mark.parametrize(
        "text",
        ["hey how are you", "i like pictures of nature", "my day was good", "nice photo of yours"],
    )
    def test_ignores_normal_chat(self, text):
        assert not P.wants_photo(text)


class TestNeverRepeats:
    def test_picks_an_unseen_photo(self):
        chosen = P.pick(LIB, [1, 2], "noc", rng=RNG)
        assert chosen["id"] == 3

    def test_returns_none_when_all_were_sent(self):
        assert P.pick(LIB, [1, 2, 3], "noc", rng=RNG) is None

    def test_never_returns_a_seen_photo_over_many_draws(self):
        for _ in range(200):
            chosen = P.pick(LIB, [1, 3], "noc", rng=random.Random())
            assert chosen["id"] == 2, "poslala by fotku, ktorú už videl"

    def test_counts_what_is_left(self):
        assert P.remaining(LIB, [1]) == 2
        assert P.remaining(LIB, []) == 3
        assert P.remaining(LIB, [1, 2, 3]) == 0

    def test_skips_inactive_photos(self):
        library = [{**LIB[0], "active": False}]
        assert P.pick(library, [], "noc", rng=RNG) is None


class TestSituationFits:
    def test_afternoon_gets_the_city_photo(self):
        assert P.pick(LIB, [], "poobede", rng=RNG)["id"] == 2

    def test_night_gets_the_bed_photo(self):
        assert P.pick(LIB, [], "noc", rng=RNG)["id"] in (1, 3)

    def test_spicy_preferred_when_he_pushes(self):
        assert P.pick(LIB, [], "noc", prefer_spicy=True, rng=RNG)["id"] == 1

    def test_falls_back_when_nothing_fits_the_hour(self):
        library = [LIB[1]]  # len poobedná fotka
        assert P.pick(library, [], "noc", rng=RNG)["id"] == 2, "radšej poslať než neposlať"


class TestCooldown:
    def test_first_photo_always_allowed(self):
        assert P.cooldown_passed({"last_photo_at": None}, 45)

    def test_blocked_right_after_one(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        assert not P.cooldown_passed({"last_photo_at": recent}, 45)

    def test_allowed_after_the_wait(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        assert P.cooldown_passed({"last_photo_at": old}, 45)


class TestPhotoInFlow:
    def _library_db(self, bot, db, library, seen=()):
        db.photos = list(library)
        db.photo_seen = list(seen)
        db.photo_sends = []

        async def photo_library():
            return list(db.photos)

        async def photos_sent_to(_tg_id):
            return list(db.photo_seen)

        async def record_photo_send(photo_id, tg_id):
            db.photo_sends.append((photo_id, tg_id))

        db.photo_library = photo_library
        db.photos_sent_to = photos_sent_to
        db.record_photo_send = record_photo_send

    def test_prompt_describes_the_photo_being_sent(self, monkeypatch):
        bot, db, llm, _, _ = build(
            user_row(msg_count=6),
            [{"role": "user", "content": "send me a pic"}],
            "here you go",
            behavior=NO_WINDOW,
        )
        self._library_db(bot, db, LIB)
        monkeypatch.setattr(bot, "_send_photo", _noop_send)
        asyncio.run(bot.reply_to(555))
        assert "PRÁVE MU POSIELAŠ FOTKU" in llm.prompts[0]

    def test_prompt_handles_having_no_photo(self, monkeypatch):
        bot, db, llm, _, _ = build(
            user_row(msg_count=6),
            [{"role": "user", "content": "send me a pic"}],
            "maybe later",
            behavior=NO_WINDOW,
        )
        self._library_db(bot, db, [])
        asyncio.run(bot.reply_to(555))
        assert "FOTKU PÝTA, ALE ŽIADNU NEPOSIELAŠ" in llm.prompts[0]

    def test_no_photo_section_when_he_did_not_ask(self, monkeypatch):
        bot, db, llm, _, _ = build(
            user_row(msg_count=6),
            [{"role": "user", "content": "hows your evening"}],
            "quiet one",
            behavior=NO_WINDOW,
        )
        self._library_db(bot, db, LIB)
        asyncio.run(bot.reply_to(555))
        assert "POSIELAŠ FOTKU" not in llm.prompts[0]

    def test_link_reminder_when_already_sent(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=10, link_push_count=1, funnel_stage="link_sent"),
            [{"role": "user", "content": "send nudes babe"}],
            "you already have it",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "ODKAZ UŽ MÁ" in llm.prompts[0]


async def _noop_send(_tg_id, _photo):
    return None


class TestIncomingPhotos:
    """Keď fotku pošle on — normálnu ohodnotí, explicitnú posunie na platformu."""

    def test_explicit_photo_triggers_platform_invite(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "[poslal EXPLICITNÚ fotku: close up of male genitals]"}],
            "juuu pekny",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "POSLAL TI EXPLICITNÚ FOTKU" in prompt
        assert "pozvi ho na svoju stránku" in prompt.lower() or "stránku" in prompt

    def test_normal_photo_gets_a_normal_reaction(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "[poslal fotku: man smiling in a car, sunglasses]"}],
            "nice one",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "POSLAL TI FOTKU" in prompt
        assert "POSLAL TI EXPLICITNÚ FOTKU" not in prompt

    def test_no_photo_section_for_plain_text(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "hey how are you"}],
            "good",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "POSLAL TI" not in llm.prompts[0]


class TestForeignInFlow:
    def test_prompt_tells_her_she_does_not_understand(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=5),
            [{"role": "user", "content": "ahoj ako sa mas dnes"}],
            "sorry i only speak english 🙈",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "NAPÍSAL TI V INOM JAZYKU" in prompt
        assert "NEPREKLADAJ" in prompt

    def test_no_such_section_for_english(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=5),
            [{"role": "user", "content": "hey what are you up to"}],
            "not much",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "NAPÍSAL TI V INOM JAZYKU" not in llm.prompts[0]


class TestSendReason:
    """Fotka nikdy nesmie ísť len tak — vždy musí byť dôvod."""

    def test_bez_dovodu_nic(self):
        user = {"tg_id": 1, "msg_count": 3, "last_photo_at": None}
        assert P.send_reason("how was your day", user) is None

    def test_vypytal_si_ju(self):
        user = {"tg_id": 1, "msg_count": 2, "last_photo_at": None}
        assert P.send_reason("send me a pic", user) == "asked"

    def test_prva_selfie_prijde_medzi_5_a_10(self):
        for tg_id in range(1, 60):
            target = P.first_selfie_at(tg_id)
            assert P.FIRST_SELFIE_MIN <= target <= P.FIRST_SELFIE_MAX

    def test_prva_selfie_je_pre_daneho_cloveka_stabilna(self):
        assert P.first_selfie_at(4242) == P.first_selfie_at(4242)

    def test_prva_selfie_az_po_dosiahnuti_hranice(self):
        tg_id = 12345
        target = P.first_selfie_at(tg_id)
        pred = {"tg_id": tg_id, "msg_count": target - 1, "last_photo_at": None}
        po = {"tg_id": tg_id, "msg_count": target, "last_photo_at": None}
        assert P.send_reason("hey", pred) is None
        assert P.send_reason("hey", po) == "first"

    def test_prva_selfie_len_raz(self):
        tg_id = 12345
        user = {
            "tg_id": tg_id,
            "msg_count": P.first_selfie_at(tg_id) + 30,
            "last_photo_at": "2026-08-12T10:00:00+00:00",
        }
        assert P.send_reason("hey", user, gap_hours=0.0) is None

    def test_po_dlhom_tichu_moze_nahodit(self):
        user = {"tg_id": 7, "msg_count": 40, "last_photo_at": "2026-08-01T10:00:00+00:00"}
        always = random.Random(); always.random = lambda: 0.0
        never = random.Random(); never.random = lambda: 0.99
        assert P.send_reason("hey", user, gap_hours=30, rng=always) == "revive"
        assert P.send_reason("hey", user, gap_hours=30, rng=never) is None

    def test_kratke_ticho_nenahadzuje(self):
        user = {"tg_id": 7, "msg_count": 40, "last_photo_at": "2026-08-01T10:00:00+00:00"}
        always = random.Random(); always.random = lambda: 0.0
        assert P.send_reason("hey", user, gap_hours=2, rng=always) is None


class TestStrictTime:
    """Sama od seba nepošle fotku z pláže o druhej v noci."""

    LIBRARY = [{"id": 1, "active": True, "parts": ["poobede"], "caption": "plaz"}]

    def test_sama_radsej_nic_ako_nesediace(self):
        assert P.pick(self.LIBRARY, [], "noc", strict_time=True) is None

    def test_ked_si_vypytal_posle_aj_nesediacu(self):
        chosen = P.pick(self.LIBRARY, [], "noc", strict_time=False)
        assert chosen and chosen["id"] == 1

    def test_sediacu_posle_aj_pri_strict(self):
        chosen = P.pick(self.LIBRARY, [], "poobede", strict_time=True)
        assert chosen and chosen["id"] == 1


class TestPhotoFilename:
    """Bez názvu s príponou pošle Telethon fotku ako neotvoriteľný dokument."""

    def test_z_url_vezme_priponu(self):
        assert userbot.photo_filename("https://x.co/model-photos/tgai/a-b.png") == "photo.png"

    def test_ignoruje_query_string(self):
        assert userbot.photo_filename("https://x.co/a.jpeg?token=abc") == "photo.jpeg"

    def test_neznamy_format_ide_ako_jpg(self):
        assert userbot.photo_filename("https://x.co/a.heic") == "photo.jpg"

    def test_bez_pripony_ide_ako_jpg(self):
        assert userbot.photo_filename("https://x.co/model-photos/tgai/abc") == "photo.jpg"


class TestReakciaNaFotku:
    """Srdiečko na bežnú fotku, plamienok na horúcu — a nikdy to nesmie padnúť."""

    class FakeKlient:
        def __init__(self, zlyhaj=False):
            self.poslane = []
            self.zlyhaj = zlyhaj

        async def get_input_entity(self, tg_id):
            return tg_id

        async def __call__(self, request):
            if self.zlyhaj:
                raise RuntimeError("reactions are not available")
            self.poslane.append(request.reaction[0].emoticon)

    @pytest.fixture(autouse=True)
    def bez_cakania(self, monkeypatch):
        """Reakcia má v praxi pár sekúnd oneskorenie — v testoch ho nechceme."""
        async def hned(_s):
            return None
        monkeypatch.setattr(asyncio, "sleep", hned)

    def _bot(self, zlyhaj=False):
        bot, db, _llm, _client, _notes = build(user_row(), [], "ok")
        bot._client = self.FakeKlient(zlyhaj)
        return bot

    def test_bezna_fotka_dostane_srdiecko(self):
        bot = self._bot()
        asyncio.run(bot._react_to_photo(555, 42, explicit=False))
        assert bot._client.poslane == ["❤️"]

    def test_horuca_fotka_dostane_plamienok(self):
        bot = self._bot()
        asyncio.run(bot._react_to_photo(555, 42, explicit=True))
        assert bot._client.poslane == ["🔥"]

    def test_bez_id_spravy_sa_nic_nedeje(self):
        bot = self._bot()
        asyncio.run(bot._react_to_photo(555, 0, explicit=True))
        assert bot._client.poslane == []

    def test_zlyhanie_reakcie_nezhodi_odpoved(self):
        bot = self._bot(zlyhaj=True)
        asyncio.run(bot._react_to_photo(555, 42, explicit=True))  # nesmie vyhodiť


class TestKolekcie:
    """Po fotke z postele má prísť ďalšia z tej istej postele, nie z párty."""

    KNIZNICA = [
        {"id": 1, "active": True, "parts": [], "collection": "postel"},
        {"id": 2, "active": True, "parts": [], "collection": "postel"},
        {"id": 3, "active": True, "parts": [], "collection": "party"},
        {"id": 4, "active": True, "parts": [], "collection": ""},
    ]

    def test_pokracuje_v_kolekcii(self):
        for _ in range(30):
            chosen = P.pick(self.KNIZNICA, [1], "vecer", same_set=True)
            assert chosen["id"] == 2, "má pokračovať fotkou z tej istej postele"

    def test_bez_nadvaznosti_kolekciu_nedrzi(self):
        """Keď séria už nepokračuje, výber sa na ňu neviaže."""
        vysledky = {P.pick(self.KNIZNICA, [1], "vecer")["id"] for _ in range(40)}
        assert len(vysledky) > 1, "mimo okna sa nemá držať tej istej série"

    def test_ked_je_kolekcia_vycerpana_vezme_ine(self):
        chosen = P.pick(self.KNIZNICA, [2, 1], "vecer")
        assert chosen["id"] in (3, 4)

    def test_bez_kolekcie_neobmedzuje(self):
        vysledky = {P.pick(self.KNIZNICA, [4], "vecer")["id"] for _ in range(40)}
        assert len(vysledky) > 1, "fotka bez kolekcie nesmie zúžiť výber"

    def test_prva_fotka_bez_historie(self):
        assert P.pick(self.KNIZNICA, [], "vecer") is not None

    def test_denna_doba_ma_prednost_pred_kolekciou(self):
        kniznica = [
            {"id": 1, "active": True, "parts": ["noc"], "collection": "postel"},
            {"id": 2, "active": True, "parts": ["poobede"], "collection": "postel"},
        ]
        assert P.pick(kniznica, [1], "noc", strict_time=True) is None


class TestPoVymazaniHistorie:
    """Po vymazaní chatu nemá odstup od poslednej odpovede žiadnu hodnotu."""

    def test_prazdny_odstup_nepadne(self):
        user = {"tg_id": 7, "msg_count": 40, "last_photo_at": "2026-08-01T10:00:00+00:00"}
        assert P.send_reason("hey", user, gap_hours=None) is None

    def test_prazdny_odstup_pri_prvej_selfie(self):
        user = {"tg_id": 12345, "msg_count": 99, "last_photo_at": None}
        assert P.send_reason("hey", user, gap_hours=None) == "first"


class TestDokazFotkou:
    """Kto už fotku videl, dostane pri obvinení ďalšiu — odmietnutie ho stratí."""

    def test_ziada_dokaz_a_rovno_fotku(self):
        """Keď si v tej istej vete pýta fotku, ide bežnou cestou."""
        user = {"tg_id": 7, "msg_count": 20, "last_photo_at": "2026-08-01T10:00:00+00:00"}
        assert P.send_reason("prove it, send me a pic", user) == "asked"

    def test_dokaz_bez_priamej_ziadosti_o_fotku(self):
        user = {"tg_id": 7, "msg_count": 20, "last_photo_at": "2026-08-01T10:00:00+00:00"}
        assert P.send_reason("show me that you are real", user) == "proof"

    def test_kto_ziadnu_nevidel_sa_k_nej_nedostane(self):
        """Cez obvinenie z bota sa nedá vytiahnuť prvá fotka."""
        user = {"tg_id": 7, "msg_count": 2, "last_photo_at": None}
        assert P.send_reason("show me that you are real", user) is None



class TestOknoSerie:
    """Séria je „takto som teraz oblečená", nie zásoba na ďalší deň."""

    @staticmethod
    def _pred(minut):
        from datetime import datetime, timedelta, timezone
        teraz = datetime.now(timezone.utc)
        return {"last_photo_at": (teraz - timedelta(minutes=minut)).isoformat()}, teraz

    def test_hned_po_fotke_moze_pokracovat(self):
        user, teraz = self._pred(3)
        vzdy = random.Random(); vzdy.random = lambda: 0.0
        assert P.set_continues(user, teraz, vzdy)

    def test_po_desiatich_minutach_uz_nie(self):
        user, teraz = self._pred(25)
        vzdy = random.Random(); vzdy.random = lambda: 0.0
        assert not P.set_continues(user, teraz, vzdy)

    def test_na_druhy_den_uz_vobec(self):
        user, teraz = self._pred(60 * 23)
        vzdy = random.Random(); vzdy.random = lambda: 0.0
        assert not P.set_continues(user, teraz, vzdy)

    def test_ani_v_okne_nie_zakazdym(self):
        user, teraz = self._pred(3)
        nikdy = random.Random(); nikdy.random = lambda: 0.99
        assert not P.set_continues(user, teraz, nikdy)

    def test_bez_predoslej_fotky_nic(self):
        assert not P.set_continues({})
