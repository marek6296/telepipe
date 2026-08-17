"""Denný rozvrh — deň, ktorý existuje aj keď nikto nepíše."""
from datetime import date, datetime, timedelta

import den as D


class TestStabilita:
    """Rovnaký deň musí vyzerať rovnako, inak si o pol hodiny protirečí."""

    def test_ten_isty_den_dva_krat_rovnako(self):
        a = D.plan(date(2026, 8, 17), "simona")
        b = D.plan(date(2026, 8, 17), "simona")
        assert a == b

    def test_ine_dni_su_ine(self):
        a = D.plan(date(2026, 8, 17), "simona")
        b = D.plan(date(2026, 8, 18), "simona")
        assert a != b

    def test_dve_modelky_nemaju_rovnaky_den(self):
        a = D.plan(date(2026, 8, 17), "simona")
        b = D.plan(date(2026, 8, 17), "mio")
        assert a != b


class TestSuvislost:
    def test_bloky_na_seba_nadvazuju_bez_dier(self):
        for offset in range(7):
            bloky = D.plan(date(2026, 8, 17 + offset), "simona")
            for skorsi, neskorsi in zip(bloky, bloky[1:]):
                assert skorsi.do == neskorsi.od, f"diera medzi {skorsi} a {neskorsi}"

    def test_den_ide_dopredu(self):
        """Nulový blok nikdy nenastane a v rozvrhu len zavadzia.

        Stalo sa to v utorok: po dlhom fotení bol `kurzor` už za osemnástou,
        takže „na ceste domov" vyšlo od 18:07 do 18:07.
        """
        for offset in range(14):
            d = date(2026, 8, 17) + timedelta(days=offset)
            for seed in ("tgai", "tgmio", "tgayko"):
                for b in D.plan(d, seed):
                    assert b.do > b.od, f"{seed} {d}: blok {b} nemá dĺžku"

    def test_kazdy_blok_ma_miestnost_aj_popis(self):
        for b in D.plan(date(2026, 8, 19), "simona"):
            assert b.co, "bez popisu nemá čo povedať"
            assert isinstance(b.kde, str)
            assert b.odozva > 0


class TestPevneBody:
    def test_v_utorok_a_stvrtok_foti(self):
        # 2026-08-18 je utorok, 2026-08-20 štvrtok.
        for d in (date(2026, 8, 18), date(2026, 8, 20)):
            assert any("fotení" in b.co for b in D.plan(d, "simona")), d

    def test_v_pondelok_stredu_piatok_cvici(self):
        for d in (date(2026, 8, 17), date(2026, 8, 19), date(2026, 8, 21)):
            assert any(b.kde == "gym" for b in D.plan(d, "simona")), d

    def test_na_foteni_je_dlho_nedostupna(self):
        bloky = [b for b in D.plan(date(2026, 8, 18), "simona") if "fotení" in b.co]
        assert bloky and bloky[0].odozva >= 3.0
        assert D.busy(bloky[0])


class TestKdeJePrave:
    def test_najde_blok_podla_hodiny(self):
        # Poludnie ešte spí alebo práve vstáva — v každom prípade blok existuje
        # niekedy popoludní.
        v_case = datetime(2026, 8, 17, 15, 0)
        blok = D.block_at(v_case, "simona")
        assert blok is not None
        assert blok.obsahuje(15 * 60)

    def test_po_polnoci_dobieha_vcerajsi_vecer(self):
        blok = D.block_at(datetime(2026, 8, 18, 1, 0), "simona")
        assert blok is not None, "o jednej v noci ešte nespí, okno je do 02:30"

    def test_rano_je_mimo_rozvrhu(self):
        assert D.block_at(datetime(2026, 8, 17, 7, 0), "simona") is None


class TestOdvodene:
    def test_odkial_znie_hlasovka(self):
        gym = D.Blok(0, 10, "gym", "je v posilňovni", 2.4)
        assert D.where(gym) == "gym"
        assert D.where(None, fallback="cafe") == "cafe"
        # Blok bez miestnosti („none" na fotení) nemá prebiť nastavenie mlčky.
        assert D.where(D.Blok(0, 10, "", "x", 1.0), fallback="home") == "home"

    def test_tempo_odpovedi(self):
        assert D.pace(D.Blok(0, 10, "gym", "x", 2.4)) == 2.4
        assert D.pace(None) == 1.0

    def test_popis_pre_prompt(self):
        assert D.describe(D.Blok(0, 10, "home", "leží na gauči", 0.5)) == "leží na gauči"
        assert D.describe(None) == ""

    def test_vypis_dna_je_citatelny(self):
        riadky = D.summary(date(2026, 8, 17), "simona")
        assert riadky and ":" in riadky[0] and "×" in riadky[0]


class TestVypisVBotovi:
    """`/den` je jediný spôsob, ako rozvrh skontrolovať — musí prežiť.

    Chýbajúci import `datetime` v tej metóde by bol pád za behu a žiadny
    iný test by ho nechytil.
    """

    def test_prikaz_den_vypise_rozvrh(self):
        import asyncio
        from config import Config
        from control_bot import ControlBot

        cfg = Config(
            tg_api_id=1, tg_api_hash="h", tg_session="s", control_bot_token="t",
            owner_chat_id=5, owner_as_client=False,
            supabase_url="https://x", supabase_key="k", supabase_schema="tgai",
            llm_key="k", llm_base_url="https://x/v1", model="m", summary_model="m",
            reasoning_effort="low", vision_model="v", audio_model="a",
            context_messages=12, summary_every=15, skip_contacts=True,
            contact_exceptions=frozenset(), link_min_messages=6,
            link_cooldown_hours=48, link_max_pushes=3,
        )

        class FakeDb:
            async def get_behavior(self):
                return {"active_tz": "America/Los_Angeles"}

        odpovede = []

        class FakeEvent:
            async def reply(self, text, **_kw):
                odpovede.append(text)

        bot = ControlBot(cfg, FakeDb(), None)
        asyncio.run(bot._send_day(FakeEvent()))

        assert odpovede, "príkaz musí niečo odpovedať"
        assert "Dnešok" in odpovede[0]
        assert "Odpovede:" in odpovede[0]


class TestRealneCasy:
    """Fitko od 14:00 do 15:30 je rozvrh z papiera. Človek príde 14:03."""

    def test_hranice_niesu_okruhle(self):
        okruhle = 0
        spolu = 0
        for offset in range(21):
            d = date(2026, 8, 17) + timedelta(days=offset)
            for b in D.plan(d, "tgai"):
                spolu += 1
                if b.od % 15 == 0:
                    okruhle += 1
        assert okruhle / spolu < 0.15, f"{okruhle}/{spolu} hraníc je na štvrťhodine"

    def test_kazdy_den_v_tyzdni_je_iny(self):
        """Kým mal pondelok a streda ten istý tvar, po týždni bolo vidieť vzor."""
        tvary = set()
        for offset in range(7):
            d = date(2026, 8, 17) + timedelta(days=offset)
            tvary.add(tuple(b.kde for b in D.plan(d, "tgai")))
        assert len(tvary) == 7, "každý deň v týždni musí mať vlastný priebeh"

    def test_pozna_gauc_postel_aj_kuchynu(self):
        miesta = set()
        for offset in range(7):
            d = date(2026, 8, 17) + timedelta(days=offset)
            miesta |= {b.kde for b in D.plan(d, "tgai")}
        for kde in ("home", "bedroom", "kitchen", "bathroom", "gym", "outside", "cafe", "car"):
            assert kde in miesta, f"{kde} sa v týždni nevyskytuje"


class TestPrechody:
    """Keď dopísala z fitka a teraz je v aute, povie to sama."""

    def test_hned_po_prechode_vie_ze_sa_presunula(self):
        d = date(2026, 8, 17)
        bloky = [b for b in D.plan(d, "tgai") if b.prichod]
        assert bloky, "aspoň niektoré bloky musia mať príchod"
        b = bloky[1]
        chvila = datetime(d.year, d.month, d.day, b.od // 60, b.od % 60) + timedelta(minutes=5)
        assert D.just_moved(chvila, "tgai") is not None
        assert D.arrival(D.just_moved(chvila, "tgai"))

    def test_po_case_uz_o_presune_nehovori(self):
        d = date(2026, 8, 17)
        b = [x for x in D.plan(d, "tgai") if x.prichod][1]
        neskor = datetime(d.year, d.month, d.day, b.od // 60, b.od % 60) + timedelta(minutes=50)
        assert D.just_moved(neskor, "tgai") is None

    def test_bez_bloku_ziadny_presun(self):
        assert D.just_moved(datetime(2026, 8, 17, 7, 0), "tgai") is None
        assert D.arrival(None) == ""
