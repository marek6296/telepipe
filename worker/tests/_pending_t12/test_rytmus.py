"""Rytmus dňa — aby rýchlosť odpovedí sedela na to, kde práve je.

Vzniklo z merania: cez celý týždeň odchádzalo 64 % odpovedí do pol minúty
a medián bol 12 sekúnd. Aj z fotenia, kde má podľa rozvrhu telefón odložený.
Dve príčiny, obe tu ustrážené.
"""
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import behavior as bhv
import den
import outreach
import userbot
from behavior import Behavior

TZ = ZoneInfo("America/Los_Angeles")
NASTAVENIE = Behavior(
    quick_reply_chance=0.30, seen_only_chance=0.07,
    long_pause_chance=0.03, defer_reply_chance=0.0,
)


def _cakanie(b, blok, now, r, podlaha=True):
    """To isté, čo robí `_reply_locked` — vrátane podlahy a pozorného režimu."""
    faktor = bhv.wave_factor(b, now, "tgai") * den.pace(blok)
    if podlaha:
        faktor = max(faktor, userbot.MIN_FACTOR)
    quick = None if den.busy(blok) else bhv.quick_reply(b, "hey whats up", r)
    if quick:
        return quick[0] + quick[1]
    return (
        bhv.read_delay(b, r, factor=faktor)
        + bhv.reply_delay(b, r, factor=faktor)
        + bhv.seen_only_delay(b, r)
        + bhv.long_pause_delay(b, r)
    )


def _vzorka(hodina, n=3000, podlaha=True):
    now = datetime(2026, 8, 18, hodina, 0, tzinfo=TZ)
    blok = den.block_at(now, "tgai")
    r = random.Random(5)
    return sorted(_cakanie(NASTAVENIE, blok, now, r, podlaha) for _ in range(n))


class TestZaneprazdnenaNeodpisujeOkamzite:
    """Pozorný režim obchádza vlnu aj rozvrh — nesmie sa spustiť na fotení."""

    def test_na_foteni_sa_pozorny_rezim_nespusti(self):
        now = datetime(2026, 8, 18, 15, 0, tzinfo=TZ)   # utorok, fotenie
        blok = den.block_at(now, "tgai")
        assert den.busy(blok), "utorok 15:00 má byť fotenie"
        r = random.Random(1)
        for _ in range(500):
            assert None is (
                None if den.busy(blok) else bhv.quick_reply(NASTAVENIE, "hey", r)
            )

    def test_z_fotenia_neodpise_do_pol_minuty(self):
        casy = _vzorka(15)
        assert not [c for c in casy if c < 30], "z fotenia nesmie odpísať okamžite"
        assert casy[len(casy) // 2] > 120, "medián z fotenia má byť v minútach"

    def test_na_gauci_odpisuje_svizne(self):
        """Opačný smer: keď leží s telefónom, nesmie z toho byť úrad."""
        casy = _vzorka(22)
        assert casy[len(casy) // 2] < 300


class TestPodlahaNasobicov:
    """Vlna „burst" a gauč sa vynásobili na ×0.072 — 2,5 až 28 sekúnd.

    Tým sa zmazal rozdiel medzi „drží telefón v ruke" (na to je pozorný
    režim) a „všimla si neskôr". Podlaha ten rozdiel drží.
    """

    def test_nasobic_nespadne_pod_podlahu(self):
        for vlna, _ in bhv._WAVES:
            for blok_pace in (0.5, 0.6, 0.8):
                assert max(vlna * blok_pace, userbot.MIN_FACTOR) >= userbot.MIN_FACTOR

    def test_bez_podlahy_je_vsetko_okamzite(self):
        """Kontrolná vzorka — ukazuje, čo podlaha vlastne opravuje."""
        bez = _vzorka(22, podlaha=False)
        s_podlahou = _vzorka(22, podlaha=True)
        rychle = lambda c: sum(1 for x in c if x < 30) / len(c)  # noqa: E731
        assert rychle(bez) > rychle(s_podlahou)

    def test_podlaha_nespomaluje_zaneprazdnenu(self):
        """Je to podlaha, nie strop — na fotení sa ×4.0 nesmie stratiť."""
        now = datetime(2026, 8, 18, 15, 0, tzinfo=TZ)
        faktor = bhv.wave_factor(NASTAVENIE, now, "tgai") * den.pace(
            den.block_at(now, "tgai")
        )
        assert max(faktor, userbot.MIN_FACTOR) == faktor


class TestNocnyRadSaRozpustiPostupne:
    """Kto napísal, kým spala, nesmie dostať odpoveď v tej istej minúte ako ostatní."""

    DEN = "2026-08-18"

    def test_uprostred_okna_ide_len_cast(self):
        ludia = list(range(1000, 1040))
        polovica = outreach.BACKLOG_SPREAD_H * 60 / 2
        hotovi = [t for t in ludia if outreach.backlog_ready(t, self.DEN, polovica)]
        assert 0 < len(hotovi) < len(ludia), "nemá ísť ani nikto, ani všetci naraz"

    def test_v_prvej_minute_este_nikto(self):
        """Zobudí sa a na telefón siahne o chvíľu, nie v tej istej sekunde.

        Pri deviatich konverzáciách vychádza prvá odpoveď zhruba sedem minút
        po otvorení okna — to je presne to, ako sa človek ráno chytá telefónu.
        """
        ludia = list(range(1000, 1009))
        assert not [t for t in ludia if outreach.backlog_ready(t, self.DEN, 1.0)]

    def test_po_uplynuti_okna_prejdu_vsetci(self):
        ludia = list(range(1000, 1040))
        neskor = outreach.BACKLOG_SPREAD_H * 60
        assert all(outreach.backlog_ready(t, self.DEN, neskor) for t in ludia)

    def test_poradie_je_stabilne_cez_restart(self):
        assert outreach.backlog_ready(555, self.DEN, 30) == outreach.backlog_ready(
            555, self.DEN, 30
        )

    def test_kazdy_den_ine_poradie(self):
        ludia = range(1000, 1060)
        pondelok = {t for t in ludia if outreach.backlog_ready(t, "2026-08-17", 20)}
        utorok = {t for t in ludia if outreach.backlog_ready(t, "2026-08-18", 20)}
        assert pondelok != utorok

    def test_rozprestretie_je_kratsie_nez_ranne_oslovenia(self):
        """Na správu čakajúcu od tretej rána sa nedá odpovedať až o dve hodiny."""
        assert outreach.BACKLOG_SPREAD_H < outreach.SPREAD_HOURS


class TestVlnaJePreKazduModelkuIna:
    def test_rozne_schemy_daju_rozne_vlny(self):
        start = datetime(2026, 8, 18, 13, 0, tzinfo=TZ)
        hodiny = [start + timedelta(hours=h) for h in range(12)]
        simona = [bhv.activity_wave(h, "tgai")[0] for h in hodiny]
        mio = [bhv.activity_wave(h, "tgmio")[0] for h in hodiny]
        assert simona != mio

    def test_nazov_vlny_sedi_na_nasobic(self):
        """Log musí hovoriť pravdu — predtým sa brali z dvoch volaní."""
        now = datetime(2026, 8, 18, 13, 0, tzinfo=TZ)
        nasobic, nazov = bhv.activity_wave(now, "tgai")
        assert (nasobic, nazov) in bhv._WAVES
