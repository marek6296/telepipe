"""End-to-end test toku odpovedania s fake Telegramom, DB a LLM."""
import asyncio
from datetime import datetime, timedelta, timezone

import behavior as bhv
import humanize
import pytest
from config import TenantConfig as Config
import userbot
from userbot import UserBot

# celý tok odpovede — bez tejto fixture by testy reálne spali minúty
pytestmark = pytest.mark.usefixtures("fast")

PERSONA = {
    "name": "Lucia",
    "age": 23,
    "city": "Bratislava",
    "backstory": "Studuje dizajn.",
    "tone": "hrava",
    "msg_style": "kratke spravy",
    "boundaries": "",
    "funnel_rules": "najprv sa bav",
    "cta_link": "https://fanvue.com/lucia",
    "extra_rules": "",
}


def make_config(**overrides):
    base = dict(
        model_id="test-model",
        account_id="acc-1",
        name="Lucia",
        tg_api_id=1,
        tg_api_hash="hash",
        tg_session="sess",
        control_bot_token="token",
        owner_chat_id=999,
        owner_as_client=False,
        # V Telepipe je supabase_schema seed pre denný rozvrh/aktivitu a prefix
        # storage ciest — "tgai" drží rovnaký seed ako predloha.
        supabase_schema="tgai",
        llm_key="key",
        llm_base_url="https://api.atlascloud.ai/v1",
        model="m",
        summary_model="m",
        reasoning_effort="low",
        vision_model="google/gemini-3.5-flash",
        context_messages=12,
        summary_every=15,
        skip_contacts=True,
        contact_exceptions=frozenset(),
        link_min_messages=6,
        link_cooldown_hours=48,
        link_max_pushes=3,
    )
    base.update(overrides)
    return Config(**base)


class FakeDb:
    def __init__(self, user, messages=None, paused=False, behavior=None):
        self.behavior = behavior or {"active_start_min": 0, "active_end_min": 0}
        self.links_last_hour = 0
        self.facts_rows = []
        self.fact_plans = []
        self.claim_rows = []
        self.judge_logs = []
        self.users = {user["tg_id"]: dict(user)}
        self.messages = list(messages or [])
        self.paused = paused
        self.patches = []

    async def get_user(self, tg_id):
        row = self.users.get(tg_id)
        return dict(row) if row else None

    async def ensure_user(self, tg_id, username, first_name, lang):
        row = self.users.setdefault(
            tg_id,
            {"tg_id": tg_id, "username": username, "first_name": first_name, "lang": lang},
        )
        return dict(row)

    async def update_user(self, tg_id, patch):
        self.patches.append(patch)
        self.users[tg_id].update(patch)

    async def claim_message(self, tg_id, message_id):
        """Ako podmienený PATCH v `TenantDb`: posunie vodoznak, len ak je nižší.

        Jediný príkaz aj tu — testy tak overujú to isté pravidlo, aké nad
        riadkom vyhodnocuje Postgres.
        """
        row = self.users.get(tg_id)
        if row is None:
            return False
        if int(row.get("last_msg_id") or 0) >= int(message_id):
            return False
        row["last_msg_id"] = int(message_id)
        return True

    async def get_persona(self):
        return dict(PERSONA)

    async def get_behavior(self):
        return dict(self.behavior)

    async def links_sent_since(self, since_iso):
        return self.links_last_hour

    async def people_since(self, since_iso):
        """Komu za hodinu odišla správa. Testy si to nastavia cez `oslovenych`."""
        return list(getattr(self, "oslovenych", []))

    async def replies_since(self, since_iso):
        """Strop sa počíta aj z archívu, aby ho restart nevynuloval."""
        return sum(1 for m in self.messages if m.get("role") == "assistant")

    async def facts_for(self, tg_id):
        return list(getattr(self, 'facts_rows', []))

    async def apply_facts(self, tg_id, plan):
        self.fact_plans.append(plan)

    async def episodes_for(self, tg_id, limit=4):
        return []

    async def open_loops(self, tg_id):
        return []

    async def add_loop(self, tg_id, what):
        return None

    async def close_loop(self, loop_id):
        return None

    async def add_episode(self, tg_id, episode):
        return None

    async def search_archive(self, tg_id, query, limit=5):
        return []

    async def self_claims(self, tg_id, limit=12):
        return list(getattr(self, 'claim_rows', []))

    async def add_self_claim(self, tg_id, claim):
        return None

    async def log_judge(self, tg_id, draft, fixed, reason):
        self.judge_logs.append((draft, fixed, reason))

    async def tidy_facts(self, tg_id):
        return 0

    async def photo_library(self):
        return list(getattr(self, "photos", []))

    async def photos_sent_to(self, tg_id):
        return list(getattr(self, "photos_seen", []))

    async def record_photo_send(self, photo_id, tg_id):
        self.photos_seen = list(getattr(self, "photos_seen", [])) + [photo_id]

    async def voice_library(self):
        return list(getattr(self, "voices", []))

    async def voices_sent_to(self, tg_id):
        return list(getattr(self, "voices_seen", []))

    async def record_voice_send(self, voice_id, tg_id):
        self.voices_seen = list(getattr(self, "voices_seen", [])) + [voice_id]

    async def is_paused(self):
        return self.paused

    async def set_paused(self, paused):
        self.paused = paused

    async def tg_reply_mode(self):
        return {
            "mode": getattr(self, "reply_mode", "auto"),
            "fallback_minutes": getattr(self, "fallback_minutes", None),
        }

    async def recent_messages(self, tg_id, limit):
        return self.messages[-limit:]

    async def add_message(self, tg_id, role, content):
        self.messages.append({"role": role, "content": content})

    async def pending_users(self):
        return [dict(u) for u in self.users.values() if u.get("pending_reply")]

    async def unanswered_users(self, limit=50, stale_hours=48):
        """Rovnaká logika ako v Db — jeho správa je novšia než jej odpoveď,
        a zároveň nie je taká stará, že sa už neoplatí odpisovať."""
        hranica = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat()
        out = []
        for u in self.users.values():
            if u.get("human_takeover") or not u.get("ai_enabled", True):
                continue
            incoming, replied = u.get("last_incoming_at"), u.get("last_reply_at")
            if not incoming or incoming < hranica:
                continue
            if not replied or replied < incoming:
                out.append(dict(u))
        return out


class FakeLlm:
    def __init__(self, reply_text):
        self.reply_text = reply_text
        self.prompts = []
        self.histories = []

    async def reply(self, system_prompt, history):
        self.prompts.append(system_prompt)
        self.histories.append(list(history))
        return self.reply_text

    async def structured(self, system_prompt, content, **kw):
        """Extrakcia a sudca — nech vracajú prázdno, testujú sa inde."""
        return "[]"

    async def summarize(self, previous, transcript):
        return "zhrnutie"


class _NoopAction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeClient:
    def __init__(self):
        self.sent = []
        self.read = []
        self.files = []
        # Poradie textu a médií — na to, aby hlasovka odišla až za textom.
        self.events = []

    def action(self, *args, **kwargs):
        return _NoopAction()

    async def send_message(self, tg_id, text):
        self.sent.append((tg_id, text))
        self.events.append(("text", text))

    async def send_file(self, tg_id, buffer, **kw):
        self.files.append((tg_id, getattr(buffer, "name", ""), kw))
        self.events.append(("voice" if kw.get("voice_note") else "photo", getattr(buffer, "name", "")))

    async def send_read_acknowledge(self, tg_id):
        self.read.append(tg_id)


def build(user, messages, reply_text, cfg=None, paused=False, behavior=None):
    db = FakeDb(user, messages, paused=paused, behavior=behavior)
    llm = FakeLlm(reply_text)
    client = FakeClient()
    notes = []

    async def notify(text):
        notes.append(text)

    bot = UserBot(cfg or make_config(), db, llm, client, notify)
    return bot, db, llm, client, notes


def user_row(**kw):
    base = {
        "tg_id": 555,
        "username": "peter",
        "first_name": "Peter",
        "funnel_stage": "warm",
        "msg_count": 4,
        "link_push_count": 0,
        "link_sent_at": None,
        "paid": False,
        "ai_enabled": True,
        "human_takeover": False,
        "summary": "",
        "summary_at_msg": 0,
        "pending_reply": False,
        "reply_after": None,
        "partner_name": "",
        "name_asked": False,
        "asked_topics": {},
        "used_gags": {},
    }
    base.update(kw)
    return base


class TestReplyFlow:
    def test_sends_reply_and_stores_it(self):
        bot, db, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "co robis"}, {"role": "assistant", "content": "nic"},
             {"role": "user", "content": "a teraz?"}],
            "prave varim vecerou",
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == [(555, "prave varim vecerou")]
        assert db.messages[-1] == {"role": "assistant", "content": "prave varim vecerou"}

    def test_strips_greeting_in_ongoing_conversation(self):
        """Nedávno odpovedala → žiadny pozdrav (riadi sa medzerou, nie počtom správ)."""
        recent = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        bot, _, _, client, _ = build(
            user_row(msg_count=6, last_reply_at=recent),
            [{"role": "user", "content": "hej"}, {"role": "assistant", "content": "cau"},
             {"role": "user", "content": "co je"}],
            "Ahoj, akurat som prisla domov",
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent[0][1] == "akurat som prisla domov"

    def test_keeps_greeting_on_very_first_reply(self):
        bot, _, _, client, _ = build(
            user_row(msg_count=1),
            [{"role": "user", "content": "ahoj"}],
            "Ahoj, ako si ma nasiel?",
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent[0][1].startswith("Ahoj")

    def test_removes_link_when_funnel_forbids_it(self):
        bot, db, _, client, _ = build(
            user_row(msg_count=3, funnel_stage="warm"),
            [{"role": "user", "content": "mas fotky?"}],
            "jasne, pozri https://fanvue.com/lucia",
        )
        asyncio.run(bot.reply_to(555))
        assert "fanvue" not in client.sent[0][1]
        assert db.users[555]["funnel_stage"] == "warm"
        assert db.users[555]["link_push_count"] == 0

    def test_records_link_when_allowed_and_sent(self):
        bot, db, _, client, notes = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "kde najdem viac?"}],
            "tu mas https://fanvue.com/lucia",
        )
        asyncio.run(bot.reply_to(555))
        assert "fanvue.com/lucia" in client.sent[0][1]
        assert db.users[555]["funnel_stage"] == "link_sent"
        assert db.users[555]["link_push_count"] == 1
        assert any("Odkaz poslaný" in n for n in notes)

    def test_link_prompt_blocked_inside_cooldown(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        bot, _, llm, client, _ = build(
            user_row(msg_count=20, link_push_count=1, link_sent_at=recent, funnel_stage="warm"),
            [{"role": "user", "content": "a co dalej"}],
            "uvidime",
        )
        asyncio.run(bot.reply_to(555))
        assert "ODKAZ JE TERAZ ZAKÁZANÝ" in llm.prompts[0]

    def test_splits_multi_paragraph_reply(self):
        bot, _, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "povedz mi nieco"}],
            "prva cast\n\ndruha cast",
        )
        asyncio.run(bot.reply_to(555))
        assert [t for _, t in client.sent] == ["prva cast", "druha cast"]

    def test_skips_when_human_took_over(self):
        bot, _, _, client, _ = build(
            user_row(human_takeover=True),
            [{"role": "user", "content": "ahoj"}],
            "odpoved",
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == []

    def test_defers_when_globally_paused(self):
        bot, db, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "ahoj"}],
            "odpoved",
            paused=True,
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == []
        assert db.users[555]["pending_reply"] is True

    def test_defers_outside_active_window(self, monkeypatch):
        monkeypatch.setattr(bhv, "in_active_window", lambda *a, **k: False)
        bot, db, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "ahoj"}],
            "odpoved",
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == []
        assert db.users[555]["pending_reply"] is True

    def test_defers_when_hourly_cap_reached(self):
        bot, db, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "ahoj"}, {"role": "user", "content": "hej"}],
            "odpoved",
            behavior={"active_start_min": 0, "active_end_min": 0, "max_replies_per_hour": 1},
        )
        asyncio.run(bot.reply_to(555))
        asyncio.run(bot.reply_to(555))
        assert len(client.sent) == 1
        assert db.users[555]["pending_reply"] is True

    def test_pending_flag_cleared_after_successful_reply(self):
        bot, db, _, client, _ = build(
            user_row(pending_reply=True),
            [{"role": "user", "content": "ahoj"}],
            "odpoved",
        )
        asyncio.run(bot.reply_to(555))
        assert db.users[555]["pending_reply"] is False

    def test_summary_refreshed_after_threshold(self):
        bot, db, _, _, _ = build(
            user_row(msg_count=15, summary_at_msg=0),
            [{"role": "user", "content": "ahoj"}],
            "odpoved",
        )
        asyncio.run(bot.reply_to(555))
        assert db.users[555]["summary"] == "zhrnutie"
        assert db.users[555]["summary_at_msg"] == 15

    def test_empty_model_reply_sends_nothing(self):
        bot, _, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "ahoj"}],
            "   ",
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == []


class TestReadReceipt:
    def test_marks_conversation_as_read_before_replying(self):
        bot, _, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "hello"}],
            "hey you",
        )
        asyncio.run(bot.reply_to(555))
        assert client.read == [555], "správa sa musí označiť ako prečítaná"
        assert client.sent, "a potom odoslať odpoveď"

    def test_read_failure_does_not_block_reply(self):
        bot, _, _, client, _ = build(
            user_row(),
            [{"role": "user", "content": "hello"}],
            "hey you",
        )

        async def boom(_tg_id):
            raise RuntimeError("read failed")

        client.send_read_acknowledge = boom
        asyncio.run(bot.reply_to(555))
        assert client.sent, "zlyhanie 'prečítané' nesmie zhodiť odpoveď"


class TestDeferSurvivesRestart:
    """Naplánovaná odpoveď musí prežiť restart aj s pôvodným časom."""

    def test_defer_zapise_reply_after(self):
        bot, db, _llm, _client, _notes = build(user_row(), [], "ok")
        asyncio.run(bot._defer(555, 600))
        row = db.users[555]
        assert row["pending_reply"] is True
        stamp = datetime.fromisoformat(row["reply_after"])
        zvysok = (stamp - datetime.now(timezone.utc)).total_seconds()
        assert 570 < zvysok <= 600, f"reply_after je {zvysok} s od teraz"

    def test_len_videne_zapise_termin_pred_spanim(self, monkeypatch):
        """Kým čaká, termín už musí byť v DB — inak ho restart stratí."""
        # Fixture `fast` pauzy vypína, tu ich naopak potrebujeme.
        monkeypatch.setattr(bhv, "seen_only_delay", lambda *a, **k: 300)
        bot, db, _llm, _client, _notes = build(
            user_row(),
            [{"role": "user", "content": "hey"}],
            "hey you",
            behavior={
                # Bez vypnutého okna test padal podľa toho, koľko je v Kalifornii
                # hodín — mimo 12:12–02:30 sa odpoveď odložila a k pauze sa
                # vôbec nedostala.
                "active_start_min": 0,
                "active_end_min": 0,
                "seen_only_chance": 1.0,
                "seen_only_min_s": 300,
                "seen_only_max_s": 300,
                "quick_reply_chance": 0.0,
                "long_pause_chance": 0.0,
                "defer_reply_chance": 0.0,
            },
        )

        zachytene = {}
        povodne = bot._defer

        async def spy(tg_id, seconds):
            zachytene[tg_id] = seconds
            await povodne(tg_id, seconds)
            raise asyncio.CancelledError  # simuluje pád workera počas čakania

        bot._defer = spy
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(bot.reply_to(555))

        assert zachytene[555] == 300
        assert db.users[555]["pending_reply"] is True
        assert db.users[555]["reply_after"] is not None


class TestSweepNajdeZabudnutych:
    """Nikto nesmie ostať bez odpovede — ani keď sa `pending_reply` stratí."""

    # Rozklad nočného radu (backlog_ready) tu NIE JE témou — a je závislý od
    # skutočných hodín: okno defaultného chovania sa otvára o polnoci LA času
    # a prvých ~75 minút sweeper ľudí schválne púšťa postupne. Bez tohto by
    # celá trieda padala každý deň medzi 9:00 a 10:15 nášho času.
    @pytest.fixture(autouse=True)
    def _rad_je_vzdy_na_nom(self, monkeypatch):
        import outreach

        monkeypatch.setattr(outreach, "backlog_ready", lambda *a, **k: True)

    @staticmethod
    def _bot(**prepis):
        row = user_row(
            pending_reply=False,
            last_incoming_at=_iso(minutes_ago=5),
            last_reply_at=_iso(minutes_ago=40),
            **prepis,
        )
        return build(row, [{"role": "user", "content": "you there?"}], "sorry was busy")

    def test_dobehne_aj_bez_priznaku(self):
        bot, db, _llm, client, _notes = self._bot()
        asyncio.run(bot._sweep_once())
        assert client.sent, "sweeper mal odpísať, aj keď pending_reply bolo false"

    def test_kto_ma_odpovedane_sa_nechyta(self):
        bot, db, _llm, client, _notes = build(
            user_row(
                pending_reply=False,
                last_incoming_at=_iso(minutes_ago=40),
                last_reply_at=_iso(minutes_ago=5),
            ),
            [{"role": "user", "content": "hey"}, {"role": "assistant", "content": "hi"}],
            "nemalo odísť",
        )
        asyncio.run(bot._sweep_once())
        assert not client.sent

    def test_rucne_prevzatu_konverzaciu_nechaj(self):
        bot, db, _llm, client, _notes = self._bot(human_takeover=True)
        asyncio.run(bot._sweep_once())
        assert not client.sent

    def test_neodpisuje_pred_terminom(self):
        bot, db, _llm, client, _notes = self._bot(reply_after=_iso(minutes_ago=-30))
        asyncio.run(bot._sweep_once())
        assert not client.sent, "termín ešte nedozrel, nemala písať"


def _iso(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


class TestOdpovedaNaAktualnuSpravu:
    """Medzi načítaním správ a odoslaním odpovede ubehnú minúty až hodina.

    Kým spí, môže napísať ďalšie správy, Marek môže konverzáciu prevziať alebo
    odpoveď medzitým odíde inou cestou. `_mark_read` je tu zástupca za tie
    pauzy — beží presne medzi prvým načítaním a obnovením stavu.
    """

    @staticmethod
    def _bot_ktory_pocas_pauzy(zmena):
        bot, db, llm, client, notes = build(
            user_row(),
            [{"role": "user", "content": "hey"}],
            "odpoved",
        )

        async def mark_read(_tg_id):
            zmena(db)

        bot._mark_read = mark_read
        return bot, db, llm, client, notes

    def test_pouzije_spravu_ktora_prisla_pocas_pauzy(self):
        bot, _db, llm, client, _ = self._bot_ktory_pocas_pauzy(
            lambda db: db.messages.append({"role": "user", "content": "u still there?"})
        )
        asyncio.run(bot.reply_to(555))
        posledna = [m for m in llm.histories[0] if m["role"] == "user"][-1]
        assert "u still there?" in posledna["content"], (
            "odpovedala na staršiu správu a novšiu ignorovala"
        )
        assert client.sent, "odpoveď mala odísť"

    def test_nepise_ked_ju_marek_medzitym_prevzal(self):
        bot, _db, _llm, client, _ = self._bot_ktory_pocas_pauzy(
            lambda db: db.users[555].update({"human_takeover": True})
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == []

    def test_nepise_druhykrat_ked_odpoved_medzitym_odisla(self):
        bot, _db, _llm, client, _ = self._bot_ktory_pocas_pauzy(
            lambda db: db.messages.append({"role": "assistant", "content": "uz som odpisala"})
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == []


class TestJednoMediumNaOdpoved:
    """Hlasovka aj fotka naraz sú štyri notifikácie od človeka s mobilom."""

    HLASOVKA = {
        "id": 1, "url": "https://x.co/a.ogg", "active": True, "parts": [],
        "is_cta": False, "slot": "",
        "transcript": "the gym today was brutal honestly, my legs are done",
        "fits": "",
    }
    FOTKA = {"id": 1, "url": "https://x.co/a.jpg", "active": True, "parts": [],
             "caption": "selfie", "collection": "", "spicy": False}

    @staticmethod
    def _bot(text, monkeypatch, msg_count=6, last_photo_at=None):
        bot, db, llm, client, notes = build(
            user_row(msg_count=msg_count, last_photo_at=last_photo_at),
            [{"role": "user", "content": text}],
            "one sec",
        )
        db.voices = [dict(TestJednoMediumNaOdpoved.HLASOVKA)]
        db.photos = [dict(TestJednoMediumNaOdpoved.FOTKA)]

        async def stiahni(_url):
            return b"data"

        monkeypatch.setattr(userbot, "_download", stiahni)
        return bot, db, llm, client, notes

    def test_pri_hlasovke_sa_vlastna_fotka_odlozi(self, monkeypatch):
        # „gym" sadne na hlasovku; fotka by inak išla ako prvá selfie.
        bot, _db, _llm, client, _ = self._bot("how was the gym today", monkeypatch)
        asyncio.run(bot.reply_to(555))
        druhy = [k for k, _ in client.events if k in ("voice", "photo")]
        assert druhy == ["voice"], f"malo odísť len jedno médium, odišlo {druhy}"

    def test_vypytana_fotka_prebije_hlasovku(self, monkeypatch):
        bot, _db, _llm, client, _ = self._bot(
            "was the gym good? send me a pic", monkeypatch
        )
        asyncio.run(bot.reply_to(555))
        druhy = [k for k, _ in client.events if k in ("voice", "photo")]
        assert druhy == ["photo"], f"vypýtaná fotka má prednosť, odišlo {druhy}"

    def test_text_ide_pred_hlasovkou(self, monkeypatch):
        bot, _db, _llm, client, _ = self._bot("how was the gym today", monkeypatch)
        asyncio.run(bot.reply_to(555))
        poradie = [k for k, _ in client.events]
        assert poradie.index("text") < poradie.index("voice"), (
            "„one sec“ musí prísť pred nahrávkou, nie za ňou"
        )


class TestNocnaHlasovkaNegeneruje:
    """Rozlúčka hlasom JE tá správa — model sa nemá čo pýtať."""

    def test_model_sa_vobec_nevola(self, monkeypatch):
        nocna = {
            "id": 9, "url": "https://x.co/night.ogg", "active": True, "parts": [],
            "is_cta": False, "slot": "night",
            "transcript": "goodnight babe, talk tomorrow", "fits": "",
        }
        bot, db, llm, client, _ = build(
            user_row(),
            [{"role": "user", "content": "im off to bed"}],
            "nemalo sa generovat",
            # Okno sa práve zatvára → winding_down je True.
            behavior={"active_start_min": 0, "active_end_min": _minute_of_day(+30)},
        )
        db.voices = [nocna]

        async def stiahni(_url):
            return b"data"

        monkeypatch.setattr(userbot, "_download", stiahni)
        asyncio.run(bot.reply_to(555))

        assert llm.prompts == [], "model nemal byť volaný vôbec"
        assert [k for k, _ in client.events] == ["voice"]
        assert db.users[555]["reply_after"], "nočný zámok musí platiť aj po hlasovke"


def _minute_of_day(offset_min):
    """Minúta dňa v Kalifornii posunutá o `offset_min` — na testy okna."""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    return (now.hour * 60 + now.minute + offset_min) % (24 * 60)


class TestRanneOslovenie:
    """Ráno píše prvá — vtedy neplatí ochrana proti dvojitej odpovedi."""

    def test_normalne_neodpisuje_po_sebe(self):
        bot, db, _llm, client, _notes = build(
            user_row(),
            [{"role": "user", "content": "hey"}, {"role": "assistant", "content": "hi"}],
            "nemalo odísť",
        )
        asyncio.run(bot.reply_to(555))
        assert not client.sent

    def test_rano_napise_aj_ked_bola_posledna_ona(self):
        bot, db, _llm, client, _notes = build(
            user_row(),
            [{"role": "user", "content": "night"}, {"role": "assistant", "content": "goodnight babe"}],
            "hey, hows the new job going?",
        )
        asyncio.run(bot.reply_to(555, morning=True))
        assert client.sent, "ranné oslovenie musí odísť, aj keď písala naposledy ona"


class TestNekonecneObvinovanie:
    """Kto štvrtýkrát tvrdí, že je bot, odpoveď už nedostane."""

    @staticmethod
    def _chat(kolko):
        rows = []
        for _ in range(kolko):
            rows.append({"role": "user", "content": "ur a bot"})
            rows.append({"role": "assistant", "content": "lol ok"})
        rows.append({"role": "user", "content": "ur a bot"})
        return rows

    def test_prve_obvinenia_dostanu_odpoved(self):
        bot, _db, _llm, client, _notes = build(user_row(), self._chat(1), "lol prove ur not")
        asyncio.run(bot.reply_to(555))
        assert client.sent

    def test_po_styroch_uz_nie(self):
        bot, db, _llm, client, _notes = build(user_row(), self._chat(4), "nemalo odísť")
        asyncio.run(bot.reply_to(555))
        assert not client.sent
        assert db.users[555]["pending_reply"] is False


class TestStareSpravySaNedobiehaju:
    """Reconciler správne povie „štyri dni stará, neodpisujem".

    Sieť pod tým ho ale prebila: `unanswered_users` porovnávala len časy a
    odpísala aj na správu spred štyroch dní. Naživo tak po restarte odišla
    odpoveď na pozdrav, ktorý bol 104 hodín starý.
    """

    # Rovnaká poistka ako v TestSweepNajdeZabudnutych — rozklad nočného radu
    # je závislý od skutočných hodín a nie je témou týchto testov.
    @pytest.fixture(autouse=True)
    def _rad_je_vzdy_na_nom(self, monkeypatch):
        import outreach

        monkeypatch.setattr(outreach, "backlog_ready", lambda *a, **k: True)

    def test_stara_sprava_uz_nedostane_odpoved(self):
        bot, db, _llm, client, _ = build(
            user_row(
                pending_reply=False,
                last_incoming_at=_iso(minutes_ago=60 * 104),
                last_reply_at=None,
            ),
            [{"role": "user", "content": "hello"}],
            "nemalo odísť",
        )
        asyncio.run(bot._sweep_once())
        assert not client.sent, "na 104 hodín starú správu sa už neodpisuje"

    def test_cerstva_sprava_sa_stale_dobehne(self):
        bot, db, _llm, client, _ = build(
            user_row(
                pending_reply=False,
                last_incoming_at=_iso(minutes_ago=20),
                last_reply_at=_iso(minutes_ago=90),
            ),
            [{"role": "user", "content": "you there?"}],
            "sorry was busy",
        )
        asyncio.run(bot._sweep_once())
        assert client.sent, "čerstvá správa bez odpovede sa dobehnúť musí"


class TestKedPozdraviOn:
    """Keď pozdraví ON, musí sa smieť pozdraviť späť.

    Pravidlo „nezdrav sa, konverzácia beží" platí uprostred rozhovoru. Keď ale
    napíše „Hello", odstrelený pozdrav nechá v odpovedi trosku.
    """

    def test_na_pozdrav_sa_pozdrav_zachova(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        bot, _db, _llm, client, _ = build(
            user_row(msg_count=12, last_reply_at=recent),
            [{"role": "user", "content": "Hello"}],
            "hey you 🥰 hows your night going",
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent, "odpoveď musí odísť"
        assert client.sent[0][1].startswith("hey"), client.sent[0][1]

    def test_uprostred_rozhovoru_sa_pozdrav_stale_odstreli(self):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        bot, _db, _llm, client, _ = build(
            user_row(msg_count=12, last_reply_at=recent),
            [{"role": "user", "content": "so what did you do today"}],
            "hey i was at the gym most of the day",
        )
        asyncio.run(bot.reply_to(555))
        assert not client.sent[0][1].lower().startswith("hey")


class TestEpizodyZoSweepera:
    """Sedenie, po ktorom sa už nikto neozval, sa predtým nezapísalo nikdy.

    `_close_session` visel na prijatej správe, takže epizóda vznikla len keď
    človek po dlhom tichu napísal znova. Naživo z toho vyšlo pol epizódy na
    konverzáciu a celá vrstva pamäte bola prakticky prázdna.
    """

    @staticmethod
    def _postav():
        bot, db, _llm, _client, _notes = build(
            user_row(msg_count=8),
            [
                {"role": "user", "content": "ahoj", "created_at": _iso(minutes_ago=600)},
                {"role": "assistant", "content": "hey", "created_at": _iso(minutes_ago=599)},
                {"role": "user", "content": "co robis", "created_at": _iso(minutes_ago=598)},
            ],
            "odpoved",
        )

        async def sessions_to_close(gap_hours=6, limit=5):
            return [dict(db.users[555])]

        db.sessions_to_close = sessions_to_close
        return bot, db

    def test_dopise_epizodu_a_poznaci_si_to(self, monkeypatch):
        bot, db = self._postav()
        zapisane = []

        async def add_episode(tg_id, episode):
            zapisane.append(episode)

        db.add_episode = add_episode
        monkeypatch.setattr(
            bot._llm, "structured",
            _vrat('{"title": "vecer", "body": "bavili sa o praci", "mood": "unaveny"}'),
        )
        asyncio.run(bot._close_stale_sessions())
        assert zapisane, "epizóda za doznené sedenie sa mala zapísať"
        assert db.users[555].get("episode_at"), "musí sa poznačiť, že je vybavená"

    def test_zlyhanie_nezhodi_sweeper(self):
        bot, db = self._postav()

        async def vybuchni(gap_hours=6, limit=5):
            raise RuntimeError("databaza spadla")

        db.sessions_to_close = vybuchni
        asyncio.run(bot._close_stale_sessions())  # nesmie vyhodiť výnimku


def _vrat(hodnota):
    async def _fn(system_prompt, content, **kw):
        return hodnota
    return _fn


class TestPisatelDostaneZoznamOpakovani:
    """Toto je oprava najväčšej nameranej chyby.

    Sudca opravoval 48 % jej správ a 89 % tých opráv bolo opakovanie. Príčina:
    zoznam toho, čo už povedala, dostával LEN sudca. Pisateľ tie správy videl
    iba ako históriu rozhovoru a medzi štyridsiatimi sekciami sa jedna veta
    „neopakuj sa" stratila.
    """

    def test_jej_nedavne_spravy_su_v_systemovom_prompte(self):
        bot, _db, llm, _client, _notes = build(
            user_row(msg_count=25),
            [
                {"role": "assistant", "content": "mne je furt zima tu"},
                {"role": "user", "content": "aj mne"},
            ],
            "no vidis",
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[-1]
        assert "TOTO SI UŽ POVEDALA" in prompt
        assert "mne je furt zima tu" in prompt

    def test_sudca_ho_dostava_dalej(self):
        bot, _db, llm, _client, _notes = build(
            user_row(msg_count=25),
            [
                {"role": "assistant", "content": "mne je furt zima tu"},
                {"role": "user", "content": "aj mne"},
            ],
            "no vidis",
        )
        videne = []

        async def structured(system_prompt, content, **kw):
            videne.append(content)
            return "{}"

        llm.structured = structured
        asyncio.run(bot.reply_to(555))
        assert any("mne je furt zima tu" in c for c in videne)


class TestGenerovanaHlasovkaMaPrednost:
    """Nahratý súbor povie vždy to isté a nikdy nesadne na to, čo práve padlo.

    Preto sa stará knižnica prestala pýtať ako prvá. Ostáva len pre modelku,
    ktorá ešte nemá vyrobený hlas — pre tú je jediná možnosť, ako niečo povedať.
    """

    KNIZNICA = [{"id": 1, "active": True, "parts": [], "is_cta": False,
                 "url": "https://x/1.ogg", "slot": "",
                 "transcript": "im so tired today, gym killed me honestly",
                 "fits": "gym"}]

    @staticmethod
    def _bot(behavior_prepis):
        bot, db, llm, client, notes = build(
            user_row(msg_count=25),
            [{"role": "user", "content": "how was the gym today?"}],
            "it was rough honestly",
            # Okno 24/7, inak by test závisel na tom, o koľkej práve beží.
            behavior={"active_start_min": 0, "active_end_min": 0, **behavior_prepis},
        )
        db.voices = list(TestGenerovanaHlasovkaMaPrednost.KNIZNICA)
        return bot, db, client

    @staticmethod
    def _siahol_do_kniznice(bot) -> list:
        """Sleduje, či sa výber z nahratej knižnice vôbec spustil.

        Nedá sa to merať cez odoslané súbory: v teste sťahovanie zlyhá tak či
        tak, takže by test prešiel aj bez opravy — čo sa aj stalo.
        """
        volania = []
        povodne = bot._pick_voice

        async def sleduj(*a, **kw):
            volania.append(a)
            return await povodne(*a, **kw)

        bot._pick_voice = sleduj
        return volania

    def test_s_vyrobenym_hlasom_sa_kniznica_nepouzije(self):
        bot, _db, _client = self._bot(
            {"voices_enabled": True, "eleven_key": "k", "eleven_voice_id": "v"}
        )
        volania = self._siahol_do_kniznice(bot)
        asyncio.run(bot.reply_to(555))
        assert not volania, "keď vie hlasovku vyrobiť, knižnica sa nemá pýtať vôbec"

    def test_bez_vyrobeneho_hlasu_kniznica_zachrani(self):
        """Ayko hlas ešte nemá — pre ňu je knižnica jediná možnosť."""
        bot, _db, _client = self._bot(
            {"voices_enabled": True, "eleven_key": "", "eleven_voice_id": ""}
        )
        volania = self._siahol_do_kniznice(bot)
        asyncio.run(bot.reply_to(555))
        assert volania, "bez vlastného hlasu sa knižnica použiť má"


class TestOdpovedeStropNaLudiNebrzdi:
    """Odpoveď tomu, kto napísal prvý, sa nesmie držať kvôli počtu ľudí.

    Prvá verzia to robila a bolo to zle: kým dvanásť rozhovorov bežalo,
    trinásty človek by sa odpovede nedočkal nikdy. Objem drží strop na počet
    správ, ten stačí.
    """

    @staticmethod
    def _bot(oslovenych):
        bot, db, llm, client, notes = build(
            user_row(msg_count=10),
            [{"role": "user", "content": "hey"}],
            "hey you",
            behavior={"active_start_min": 0, "active_end_min": 0,
                      "max_outreach_per_hour": 2},
        )
        db.oslovenych = list(oslovenych)
        return bot, db, client

    def test_novy_clovek_dostane_odpoved_aj_pri_plnom_strope(self):
        bot, _db, client = self._bot([1, 2, 3, 4, 5, 6, 7, 8])
        asyncio.run(bot.reply_to(555))
        assert client.sent, "kto napísal prvý, musí dostať odpoveď"

    def test_strop_na_spravy_stale_plati(self):
        bot, db, client = self._bot([])
        db.behavior["max_replies_per_hour"] = 0
        asyncio.run(bot.reply_to(555))
        assert not client.sent
        assert db.users[555]["pending_reply"] is True


class TestFloodChybaZastaviPisanie:
    """FloodWait a PeerFlood padali doteraz do všeobecného `except`.

    Sweeper to o tri minúty skúsil znova — a to je presne postup, ktorým sa
    z dočasného obmedzenia stane trvalé.
    """

    @staticmethod
    def _bot():
        return build(
            user_row(msg_count=10),
            [{"role": "user", "content": "hey"}],
            "hey you",
            behavior={"active_start_min": 0, "active_end_min": 0},
        )

    def test_floodwait_odlozi_odpoved_a_nezopakuje_ju(self):
        from telethon.errors import FloodWaitError

        bot, db, _llm, client, _notes = self._bot()

        async def padni(tg_id, text):
            raise FloodWaitError(request=None, capture=900)

        client.send_message = padni
        asyncio.run(bot.reply_to(555))
        assert db.users[555]["pending_reply"] is True, "odpoveď má počkať"
        assert bot._flood_until is not None, "musí si zapamätať, dokedy mlčí"
        assert not asyncio.run(bot._flood_ok()), "počas pauzy sa nesmie posielať"

    def test_peerflood_zapne_globalnu_pauzu_a_ozve_sa(self):
        from telethon.errors import PeerFloodError

        bot, db, _llm, client, notes = self._bot()

        async def padni(tg_id, text):
            raise PeerFloodError(request=None)

        client.send_message = padni
        asyncio.run(bot.reply_to(555))
        assert db.paused is True, "účet označený za spam → globálna pauza"
        assert any("PeerFlood" in n or "rozposielanie" in n for n in notes), \
            "Marek sa o tomto musí dozvedieť hneď"

    def test_po_uplynuti_pauzy_pokracuje(self):
        bot, _db, _llm, _client, _notes = self._bot()
        bot._flood_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert asyncio.run(bot._flood_ok())
        assert bot._flood_until is None


class TestRozhovoryNaraz:
    """Keď píše veľa ľudí, baví sa len s pár naraz. Ostatní počkajú."""

    @staticmethod
    def _bot(aktivni, max_naraz=5):
        bot, db, llm, client, notes = build(
            user_row(msg_count=10),
            [{"role": "user", "content": "hey"}],
            "hey you",
            behavior={"active_start_min": 0, "active_end_min": 0,
                      "max_active_chats": max_naraz},
        )

        async def active_chats(since_iso, limit=200):
            return list(aktivni)

        db.active_chats = active_chats
        return bot, db, client

    def test_novy_clovek_cez_plne_miesta_pocka(self):
        bot, db, client = self._bot([1, 2, 3, 4, 5])
        asyncio.run(bot.reply_to(555))
        assert not client.sent, "nemá odpisať, keď je päť rozhovorov rozbehnutých"
        assert db.users[555]["pending_reply"] is True, "odpoveď sa má odložiť, nie zahodiť"

    def test_kto_uz_pise_pokracuje(self):
        bot, _db, client = self._bot([555, 1, 2, 3, 4])
        asyncio.run(bot.reply_to(555))
        assert client.sent, "rozbehnutý rozhovor sa nesmie preseknúť"

    def test_ked_sa_miesto_uvolni_odpise(self):
        bot, _db, client = self._bot([1, 2])
        asyncio.run(bot.reply_to(555))
        assert client.sent

    def test_vypnute_znamena_bez_obmedzenia(self):
        bot, _db, client = self._bot(list(range(30)), max_naraz=0)
        asyncio.run(bot.reply_to(555))
        assert client.sent
