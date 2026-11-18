"""Dokončenie Instagramu: štart bez pripojenia, semi karty a komentáre.

Tri veci, ktoré boli v kóde napoly:
1. agent sa pri nepripojenom účte vôbec nespustil a účet pripojený neskôr
   mlčal až do reštartu modelky,
2. semi režim posielal majiteľovi len text bez tlačidiel — nedalo sa schváliť,
3. prepínač „Reply to comments" v dashboarde nerobil nič.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import instagram_agent
import instagram_api as api
import instagram_start
from test_instagram_kolo import MOJE_ID, FakeControl, FakeDb, FakeLlm, _konverzacia, mock_threads, tick


def _cas(minus_h=0):
    return (datetime.now(timezone.utc) - timedelta(hours=minus_h)).isoformat()


# ---------------------------------------------------------------- 1) štart


class TestStartBezPripojenia:
    def _spusti(self, monkeypatch, control=None):
        db = FakeDb(connected=False)

        class FakeTenantDb:
            def __init__(self, *a, **k):
                pass

        import instagram_tenant
        monkeypatch.setattr(instagram_tenant, "TenantInstagramDb", lambda *a, **k: db)

        async def beh():
            cleanup = []
            uloha = await instagram_start.start_instagram(
                SimpleNamespace(model_id="m1"), SimpleNamespace(encryption_key="k"),
                None, FakeLlm(), cleanup, control,
            )
            uloha.cancel()
            return uloha, cleanup

        return asyncio.run(beh())

    def test_agent_bezi_aj_ked_ucet_nie_je_pripojeny(self, monkeypatch):
        uloha, cleanup = self._spusti(monkeypatch)
        assert uloha is not None, "pripojenie neskôr nesmie čakať na reštart"
        assert uloha in cleanup

    def test_zaregistruje_sa_v_control_bote(self, monkeypatch):
        control = FakeControl()
        self._spusti(monkeypatch, control)
        assert "instagram" in control.senders
        assert control.recovered_with_senders == [{"instagram"}]

    def test_nepripojene_kolo_je_necinne(self):
        agent = instagram_agent.InstagramAgent(FakeDb(connected=False), FakeLlm())
        assert asyncio.run(agent._kolo()) is False

    def test_pripojene_kolo_je_aktivne(self, monkeypatch):
        mock_threads(monkeypatch, [])
        agent = instagram_agent.InstagramAgent(FakeDb(), FakeLlm())
        assert asyncio.run(agent._kolo()) is True

    def test_necinny_agent_spi_dlhsie(self, monkeypatch):
        """Nepripojená modelka nemá chodiť do databázy každých 45 sekúnd."""
        spanky = []

        async def fake_sleep(s):
            spanky.append(s)
            raise asyncio.CancelledError

        monkeypatch.setattr(instagram_agent.asyncio, "sleep", fake_sleep)
        agent = instagram_agent.InstagramAgent(FakeDb(connected=False), FakeLlm())
        try:
            asyncio.run(agent.run())
        except asyncio.CancelledError:
            pass
        assert spanky == [instagram_agent.NECINNE_S]


# ---------------------------------------------------------------- 2) semi


def _semi(monkeypatch, llm=None, control=None, konv=None):
    db = FakeDb(reply_mode="semi")
    llm = llm or FakeLlm()
    control = control or FakeControl()
    odoslane = []
    mock_threads(monkeypatch, konv or [_konverzacia("ahoj krasavica")])

    def fake_posli(token, igsid, text, **kwargs):
        odoslane.append((igsid, text))
        return {"message_id": "out-1"}

    monkeypatch.setattr(api, "posli_text", fake_posli)
    agent = instagram_agent.InstagramAgent(db, llm, control=control)
    asyncio.run(agent._kolo())
    tick(agent, db)
    return agent, db, llm, control, odoslane


class TestSemiKarta:
    def test_karta_ide_kanalom_instagram(self, monkeypatch):
        _, _, _, control, odoslane = _semi(monkeypatch)
        assert odoslane == []
        karta = control.karty[0]
        assert karta["channel"] == "instagram"
        assert karta["conv_key"].startswith("999:")
        assert karta["display_name"] == "fan"
        assert len(karta["suggestions"]) == 3

    def test_karta_ukazuje_jeho_spravu(self, monkeypatch):
        _, _, _, control, _ = _semi(monkeypatch)
        assert "ahoj krasavica" in control.karty[0]["incoming_preview"]

    def test_navrhy_su_ocistene_od_odkazov(self, monkeypatch):
        llm = FakeLlm(navrhy=["pozri https://fanvue.com/simona", "ahoj ty 😄", "hey"])
        _, _, _, control, _ = _semi(monkeypatch, llm=llm)
        for navrh in control.karty[0]["suggestions"]:
            assert "fanvue.com" not in navrh and "http" not in navrh

    def test_navrhy_maju_instagram_pravidla(self, monkeypatch):
        _, _, llm, _, _ = _semi(monkeypatch)
        assert "Never promote or name Fanvue" in llm.prompty[0]
        assert llm.suggest_volania[0]["angles"] == instagram_agent.UHLY

    def test_ta_ista_sprava_neposle_druhu_kartu(self, monkeypatch):
        agent, _, _, control, _ = _semi(monkeypatch)
        asyncio.run(agent._kolo())
        assert len(control.karty) == 1

    def test_bez_control_bota_nic_nepadne(self, monkeypatch):
        db = FakeDb(reply_mode="semi")
        mock_threads(monkeypatch, [_konverzacia()])
        agent = instagram_agent.InstagramAgent(db, FakeLlm())
        asyncio.run(agent._kolo())  # nesmie hodiť


class TestDorucenieZKarty:
    def test_schvaleny_text_odide_a_zapise_sa(self, monkeypatch):
        agent, db, _, _, odoslane = _semi(monkeypatch)
        ok = asyncio.run(agent.deliver_text("999:1", "jasne, som tu 😄"))
        assert ok is True
        assert odoslane == []
        tick(agent, db)
        assert odoslane == [("999", "jasne, som tu 😄")]
        assert db.spravy[-1]["role"] == "assistant"
        assert db.users["999"]["msg_count"] == 1

    def test_ani_rucny_text_nepusti_odkaz(self, monkeypatch):
        agent, _, _, _, odoslane = _semi(monkeypatch)
        asyncio.run(agent.deliver_text("999:1", "tu ma najdes https://onlyfans.com/x"))
        assert odoslane == []

    def test_odpojeny_ucet_nedoruci(self, monkeypatch):
        agent, db, _, _, odoslane = _semi(monkeypatch)
        db.nastavenia["connected"] = False
        assert asyncio.run(agent.deliver_text("999:1", "ahoj")) is False
        assert odoslane == []

    def test_chyba_instagramu_vrati_false(self, monkeypatch):
        agent, db, _, _, _ = _semi(monkeypatch)

        def rozbite(token, igsid, text, **kwargs):
            raise api.InstagramError("outside of allowed window", kod=10, http_status=400)

        monkeypatch.setattr(api, "posli_text", rozbite)
        assert asyncio.run(agent.deliver_text("999:1", "ahoj")) is True
        tick(agent, db)
        assert db.queue["1"]["state"] == "blocked"


class TestOstatneTlacidla:
    def test_regenerate_vrati_nove_navrhy(self, monkeypatch):
        agent, _, llm, _, _ = _semi(monkeypatch)
        out = asyncio.run(agent.regenerate("999:1", seed="3"))
        assert len(out["suggestions"]) == 3
        assert llm.suggest_volania[-1]["seed"] == "3"

    def test_say_this_pouzije_zadanie(self, monkeypatch):
        agent, _, llm, _, _ = _semi(monkeypatch)
        asyncio.run(agent.regenerate("999:1", brief="opýtaj sa, odkiaľ je"))
        assert "opýtaj sa, odkiaľ je" in llm.prompty[-1]
        assert llm.suggest_volania[-1]["angles"] == instagram_agent.UHLY_ZADANIE

    def test_neznamy_chat_nema_navrhy(self, monkeypatch):
        agent, _, _, _, _ = _semi(monkeypatch)
        assert asyncio.run(agent.regenerate("nikto")) == {}

    def test_take_over_vypne_ai_v_chate(self, monkeypatch):
        agent, db, _, _, _ = _semi(monkeypatch)
        asyncio.run(agent.take_over("999"))
        assert db.users["999"]["human_takeover"] is True

    def test_kontext_ukaze_meno_a_rozhovor(self, monkeypatch):
        agent, _, _, _, _ = _semi(monkeypatch)
        text = asyncio.run(agent.context_card("999"))
        assert "@fan" in text and "ahoj krasavica" in text

    def test_zoznam_chatov(self, monkeypatch):
        agent, _, _, _, _ = _semi(monkeypatch)
        chaty = asyncio.run(agent.recent_chats())
        assert chaty[0]["conv_key"] == "999"

    def test_media_sa_neposielaju(self, monkeypatch):
        agent, _, _, _, _ = _semi(monkeypatch)
        assert asyncio.run(agent.photo_folders("999")) == []
        assert asyncio.run(agent.deliver_photo("999", "x", "c")) is False
        assert asyncio.run(agent.deliver_voice("999", "t", b"")) is False


# ---------------------------------------------------------------- 3) komentáre


def _prispevok(*komentare, caption="ranná káva ☕"):
    return {"id": "media-1", "caption": caption, "comments": {"data": list(komentare)}}


def _komentar(cid="c1", text="krásna fotka!", kto="fan1", kto_id="555", minus_h=1, replies=None):
    return {
        "id": cid, "text": text, "username": kto, "from": {"id": kto_id, "username": kto},
        "timestamp": _cas(minus_h), "replies": {"data": replies or []},
    }


def _komentare(monkeypatch, prispevky, llm=None, **nastavenia):
    db = FakeDb(reply_comments=True, username="simona", **nastavenia)
    llm = llm or FakeLlm("ďakujem 🥰")
    odpovede = []
    monkeypatch.setattr("instagram_delivery.select_comment", lambda *a: True)
    mock_threads(monkeypatch, [])
    monkeypatch.setattr(api, "prispevky_s_komentarmi", lambda token, limit=8, **kwargs: prispevky)

    def fake_odpoved(token, comment_id, text):
        odpovede.append((comment_id, text))
        return {"id": "r-" + comment_id}

    monkeypatch.setattr(api, "odpovedz_na_komentar", fake_odpoved)
    agent = instagram_agent.InstagramAgent(db, llm)
    asyncio.run(agent._kolo())
    if not odpovede:
        tick(agent, db)
    return agent, db, llm, odpovede


class TestKomentare:
    def test_odpovie_pod_novy_komentar(self, monkeypatch):
        _, db, _, odpovede = _komentare(monkeypatch, [_prispevok(_komentar())])
        assert len(odpovede) == 1 and odpovede[0][0] == "c1"
        assert db.queue["1"]["state"] == "sent"

    def test_druhy_krat_neodpovie(self, monkeypatch):
        agent, _, _, odpovede = _komentare(monkeypatch, [_prispevok(_komentar())])
        agent._kolo_c = 0
        asyncio.run(agent._kolo())
        assert len(odpovede) == 1

    def test_vypnute_komentare_mlcia(self, monkeypatch):
        db = FakeDb(reply_comments=False)
        mock_threads(monkeypatch, [])
        volane = []
        monkeypatch.setattr(api, "prispevky_s_komentarmi", lambda *a, **k: volane.append(1) or [])
        asyncio.run(instagram_agent.InstagramAgent(db, FakeLlm())._kolo())
        assert volane == [], "vypnuté komentáre nesmú ani míňať limit API"

    def test_v_semi_sa_komentare_nevybavuju(self, monkeypatch):
        _, _, _, odpovede = _komentare(
            monkeypatch, [_prispevok(_komentar())], reply_mode="semi"
        )
        assert odpovede == []

    def test_vlastny_komentar_preskoci(self, monkeypatch):
        _, _, _, odpovede = _komentare(
            monkeypatch, [_prispevok(_komentar(kto="simona", kto_id=MOJE_ID))]
        )
        assert odpovede == []

    def test_uz_odpovedany_rucne_preskoci(self, monkeypatch):
        moja = {"id": "r1", "username": "simona", "from": {"id": MOJE_ID}}
        _, _, _, odpovede = _komentare(
            monkeypatch, [_prispevok(_komentar(replies=[moja]))]
        )
        assert odpovede == []

    def test_stary_komentar_preskoci(self, monkeypatch):
        _, _, _, odpovede = _komentare(
            monkeypatch, [_prispevok(_komentar(minus_h=72))]
        )
        assert odpovede == []

    def test_skip_od_modelu_neodpovie_ale_zapise(self, monkeypatch):
        _, db, _, odpovede = _komentare(
            monkeypatch, [_prispevok(_komentar(text="kúp si followerov na x.com"))],
            llm=FakeLlm("SKIP"),
        )
        assert odpovede == []
        assert db.queue["1"]["state"] == "skipped"

    def test_strop_na_kolo(self, monkeypatch):
        komentare = [_komentar(cid=f"c{i}") for i in range(10)]
        _, _, _, odpovede = _komentare(monkeypatch, [_prispevok(*komentare)])
        assert len(odpovede) == 1  # one leased action; SQL enforces 10-minute comment gap

    def test_odpoved_nema_odkaz_ani_platformu(self, monkeypatch):
        llm = FakeLlm("ďakujem! viac na telegram @simona https://fanvue.com/s #hot")
        _, _, _, odpovede = _komentare(monkeypatch, [_prispevok(_komentar())], llm=llm)
        assert odpovede == []  # reject unsafe generated reply in full

    def test_prompt_je_verejny_a_bez_flirtu(self, monkeypatch):
        _, _, llm, _ = _komentare(monkeypatch, [_prispevok(_komentar())])
        assert "VEREJNÝ KOMENTÁR" in llm.prompty[0]
        assert "NEFLIRTUJ" in llm.prompty[0]

    def test_chyba_instagramu_sa_zapise_a_neopakuje(self, monkeypatch):
        db = FakeDb(reply_comments=True)
        mock_threads(monkeypatch, [])
        monkeypatch.setattr(api, "prispevky_s_komentarmi", lambda *a, **k: [_prispevok(_komentar())])

        def rozbite(token, cid, text):
            raise api.InstagramError("no permission", kod=10, http_status=400)

        monkeypatch.setattr(api, "odpovedz_na_komentar", rozbite)
        monkeypatch.setattr("instagram_delivery.select_comment", lambda *a: True)
        agent = instagram_agent.InstagramAgent(db, FakeLlm("ďakujem"))
        asyncio.run(agent._kolo())
        tick(agent, db)
        assert db.queue["1"]["state"] == "blocked"

    def test_komentare_len_v_kazdom_n_tom_kole(self, monkeypatch):
        agent, _, _, _ = _komentare(monkeypatch, [])
        volane = []
        monkeypatch.setattr(api, "prispevky_s_komentarmi", lambda *a, **k: volane.append(1) or [])
        for _ in range(instagram_agent.KOMENTARE_KAZDE - 1):
            asyncio.run(agent._kolo())
        assert volane == []
        asyncio.run(agent._kolo())
        assert volane == [1]


class TestRozoberKomentare:
    def test_prazdny_text_vynecha(self):
        out = api.rozober_komentare([_prispevok(_komentar(text="  "))], MOJE_ID)
        assert out == []

    def test_nesie_popis_prispevku(self):
        out = api.rozober_komentare([_prispevok(_komentar())], MOJE_ID)
        assert out[0]["caption"] == "ranná káva ☕"
        assert out[0]["media_id"] == "media-1"

    def test_moje_meno_spozna_aj_bez_id(self):
        out = api.rozober_komentare(
            [_prispevok(_komentar(kto="Simona", kto_id=""))], "", "simona"
        )
        assert out == []
