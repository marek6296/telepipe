"""Denný rozvrh — deň, ktorý existuje aj keď nikto nepíše."""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import den as D

MIGRACIA_022 = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "022_model_schedule.sql"
)

# Modelky, ktoré naozaj bežia. Ich deň sa nastavením rozvrhu nesmel pohnúť.
ZIVE = (
    "c7aadcde-dc94-4b82-8f5a-15d163494ff1",  # Simona
    "9f4752a2-da53-4686-adc0-18419527737c",  # Mio
    "9c5b39bb-e062-422a-9e43-25c55456dee2",  # Ayko Kuro
)


def _riadok_zo_sablony() -> dict:
    """Šablóna prehnaná cez JSON — presne to, čo príde z databázy."""
    return json.loads(json.dumps(D.SABLONA.to_row()))


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
        from config import TenantConfig as Config
        from control_bot import ControlBot

        cfg = Config(
            model_id="test-model", account_id="acc-1", name="Lucia",
            tg_api_id=1, tg_api_hash="h", tg_session="s", control_bot_token="t",
            owner_chat_id=5, owner_as_client=False,
            supabase_schema="tgai",
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
        assert "Her day" in odpovede[0]
        assert "Replies:" in odpovede[0]


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


class TestSablona:
    """Nastaviteľný rozvrh nesmie zmeniť deň modelke, ktorá si nič nenastavila.

    Simona, Mio aj Ayko bežia naživo a ich rytmus je vyladený. Migrácia 022
    z napísaného dňa spravila dáta — a jediný spôsob, ako dokázať, že sa tým
    nič nepohlo, je porovnať deň po dni.
    """

    def test_sablona_pokryva_vsetky_dni(self):
        pokryte = set()
        for c in D.SABLONA.cinnosti:
            pokryte |= set(c.dni)
        assert pokryte == set(D.VSETKY_DNI)
        assert D.SABLONA.noc is not None

    def test_rozvrh_zo_sablony_da_ten_isty_den(self):
        """Rozvrh vypísaný do dát a späť musí dať blok po bloku to isté."""
        rozvrh = D.Rozvrh.from_row(_riadok_zo_sablony())
        assert rozvrh is not None
        for seed in ZIVE:
            for offset in range(14):
                d = date(2026, 8, 17) + timedelta(days=offset)
                assert D.plan(d, seed) == D.plan(d, seed, rozvrh), f"{seed} {d}"

    def test_chybajuci_riadok_znamena_sablonu(self):
        assert D.Rozvrh.from_row(None) is None
        assert D.Rozvrh.from_row({}) is None
        # Rozvrh bez jedinej použiteľnej činnosti tiež — inak by modelka od
        # prebudenia do druhej v noci ležala v posteli a nemala čo povedať.
        assert D.Rozvrh.from_row({"activities": [{"what": "  "}]}) is None

    def test_migracia_022_sedi_na_sablonu(self):
        """SQL default a Python sú ten istý deň, napísaný dvakrát.

        Keby sa rozišli, nová modelka by dostala iný deň než tá, ktorá beží na
        šablóne — a nikto by si toho nevšimol, kým by sa niekto nespýtal, prečo
        je o šiestej v kaviarni.
        """
        sql = MIGRACIA_022.read_text(encoding="utf-8")
        vnutro = re.search(r"\$json\$(.*?)\$json\$", sql, re.S)
        assert vnutro, "v migrácii 022 nie je $json$ default pre activities"
        assert json.loads(vnutro.group(1)) == _riadok_zo_sablony()["activities"]

    def test_miestnosti_sedia_na_eleven(self):
        """`den.MIESTNOSTI` je opísaný `eleven.AMBIENCES` — nesmie sa rozísť."""
        import eleven

        assert set(D.MIESTNOSTI) == set(eleven.AMBIENCES)


class TestNastavenyRozvrh:
    """Čo si klient nastaví, to musí byť na modelke vidieť."""

    def _riadok(self, **zmeny):
        row = _riadok_zo_sablony()
        row.update(zmeny)
        return row

    def test_vlastny_den_je_iny_nez_sablona(self):
        rozvrh = D.Rozvrh.from_row(self._riadok(activities=[{
            "place": "cafe", "what": "sedí v kaviarni a kreslí", "pace": 1.2,
            "min_minutes": 60, "max_minutes": 90, "arrival": "práve si sadla",
            "days": [0, 1, 2, 3, 4, 5, 6],
        }]))
        bloky = D.plan(date(2026, 8, 17), "x", rozvrh)
        assert bloky[0].kde == "cafe"
        assert bloky[0].co == "sedí v kaviarni a kreslí"
        assert bloky[0].odozva == 1.2
        # Za poslednou činnosťou vždy dobehne noc až do konca okna.
        assert bloky[-1].do == D.KONIEC_DNA

    def test_dni_rozhoduju_o_tom_ci_sa_stane(self):
        row = self._riadok(activities=[{
            "place": "gym", "what": "je v posilňovni", "pace": 2.4,
            "min_minutes": 60, "max_minutes": 90, "arrival": "", "days": [2],
        }])
        rozvrh = D.Rozvrh.from_row(row)
        # 2026-08-19 je streda (2), 2026-08-17 pondelok (0).
        assert any(b.kde == "gym" for b in D.plan(date(2026, 8, 19), "x", rozvrh))
        assert not any(b.kde == "gym" for b in D.plan(date(2026, 8, 17), "x", rozvrh))

    def test_okno_vstavania_plati(self):
        rozvrh = D.Rozvrh.from_row(self._riadok(
            wake_weekday_start_min=540, wake_weekday_end_min=545,
        ))
        prvy = D.plan(date(2026, 8, 17), "x", rozvrh)[0]
        assert 540 <= prvy.od <= 545

    def test_prehodene_okno_sa_narovna(self):
        """Klient, ktorý napíše 13:00–11:00, nemá dostať pád `randint`."""
        rozvrh = D.Rozvrh.from_row(self._riadok(
            wake_weekday_start_min=780, wake_weekday_end_min=660,
        ))
        prvy = D.plan(date(2026, 8, 17), "x", rozvrh)[0]
        assert 660 <= prvy.od <= 780

    @pytest.mark.parametrize("zla", [
        {"place": "balkón", "what": "stojí vonku", "pace": 1, "min_minutes": 30,
         "max_minutes": 40, "days": [0]},
        {"place": "home", "what": "x", "pace": "rýchlo", "min_minutes": 30,
         "max_minutes": 40, "days": [0]},
        {"place": "home", "what": "x", "pace": 1, "min_minutes": 90,
         "max_minutes": 30, "days": [0]},
    ])
    def test_pokazena_polozka_neuskodi(self, zla):
        """Riadok od staršieho webu nesmie modelke vziať deň."""
        rozvrh = D.Rozvrh.from_row(self._riadok(activities=[zla]))
        assert rozvrh is not None
        bloky = D.plan(date(2026, 8, 17), "x", rozvrh)
        assert bloky and all(b.do > b.od for b in bloky)
        assert bloky[0].kde in D.MIESTNOSTI
        assert D.MIN_ODOZVA <= bloky[0].odozva <= D.MAX_ODOZVA

    def test_neznama_miestnost_konci_doma(self):
        rozvrh = D.Rozvrh.from_row(self._riadok(activities=[{
            "place": "balkón", "what": "stojí vonku", "pace": 1,
            "min_minutes": 30, "max_minutes": 40, "days": [0],
        }]))
        assert D.plan(date(2026, 8, 17), "x", rozvrh)[0].kde == "home"


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
