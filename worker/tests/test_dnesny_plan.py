"""Plán, ktorý sa zapisuje pre dashboard, musí byť TEN ISTÝ deň, ktorý beží.

Dashboard hovorí klientovi „práve je v posilňovni". Keby si plán losoval inak
než `den.block_at` pri odpisovaní, bola by to vymyslená veta o vlastnom
produkte — horšia než žiadna. Tieto testy držia obe cesty na jednom seede
a jednom rozvrhu.

Druhá vec, ktorú strážia: presah cez polnoc. Modelka odpisuje do 02:30 podľa
VČERAJŠIEHO plánu (`block_at` sa pozerá aj o deň dozadu). Bez presahu by
dashboard medzi polnocou a pol treťou tvrdil, že spí, hoci práve píše.
"""
from datetime import date, datetime, timedelta

import den

SEED = "tenant_simona"


def zapisane(dnes: date, rozvrh=None) -> list[dict]:
    """To isté, čo robí `UserBot._zapis_dnesok`, len bez databázy."""

    def tvar(b, posun: int = 0) -> dict:
        return {
            "od": b.od - posun,
            "do": b.do - posun,
            "kde": b.kde,
            "co": b.co,
            "odozva": b.odozva,
        }

    bloky = [
        tvar(b, 1440)
        for b in den.plan(dnes - timedelta(days=1), SEED, rozvrh)
        if b.do > 1440
    ]
    bloky += [tvar(b) for b in den.plan(dnes, SEED, rozvrh)]
    return bloky


def v_plane(bloky: list[dict], minuta: int):
    """Ako `najdiBlok` v `web/components/app/her-day.tsx`."""
    for b in bloky:
        if b["od"] <= minuta < b["do"]:
            return b
    return None


class TestPlanSediSTymCoBezi:
    """Zapísaný blok = blok, podľa ktorého v tej minúte naozaj odpisuje."""

    def test_kazda_minuta_dna_sedi(self):
        dnes = date(2026, 8, 24)
        bloky = zapisane(dnes)
        rozdiely = []
        for minuta in range(0, 1440, 7):
            teraz = datetime(dnes.year, dnes.month, dnes.day, minuta // 60, minuta % 60)
            bezi = den.block_at(teraz, SEED)
            zapis = v_plane(bloky, minuta)
            if (bezi is None) != (zapis is None):
                rozdiely.append((minuta, bezi, zapis))
            elif bezi is not None and (bezi.co != zapis["co"] or bezi.odozva != zapis["odozva"]):
                rozdiely.append((minuta, bezi.co, zapis["co"]))
        assert not rozdiely, f"dashboard by ukázal niečo iné, než modelka robí: {rozdiely[:3]}"

    def test_cely_tyzden(self):
        """Každý deň v týždni má vlastný priebeh — stačí jeden nesedieť."""
        for posun in range(7):
            dnes = date(2026, 8, 24) + timedelta(days=posun)
            bloky = zapisane(dnes)
            for minuta in range(0, 1440, 31):
                teraz = datetime(dnes.year, dnes.month, dnes.day, minuta // 60, minuta % 60)
                bezi = den.block_at(teraz, SEED)
                zapis = v_plane(bloky, minuta)
                assert (bezi is None) == (zapis is None), f"{dnes} {minuta}"


class TestPresahCezPolnoc:
    def test_po_polnoci_nie_je_prazdno(self):
        """Medzi 00:00 a 02:30 modelka ešte píše — plán to musí ukazovať."""
        dnes = date(2026, 8, 24)
        bloky = zapisane(dnes)
        skoro_rano = [m for m in range(0, 150, 5) if v_plane(bloky, m) is not None]
        assert skoro_rano, "po polnoci nie je v pláne nič, hoci modelka odpisuje"

    def test_presah_ma_zaporne_od(self):
        """Včerajšia noc sa prepočítava do dnešných minút, teda pod nulu."""
        bloky = zapisane(date(2026, 8, 24))
        assert bloky[0]["od"] < 0

    def test_test_naozaj_meria(self):
        """Bez presahu musí prvý test spadnúť — inak nekontroluje nič."""
        dnes = date(2026, 8, 24)
        bez_presahu = [
            {"od": b.od, "do": b.do, "kde": b.kde, "co": b.co, "odozva": b.odozva}
            for b in den.plan(dnes, SEED)
        ]
        teraz = datetime(dnes.year, dnes.month, dnes.day, 1, 0)
        assert den.block_at(teraz, SEED) is not None
        assert v_plane(bez_presahu, 60) is None


class TestKlientskyRozvrh:
    """Modelka s vlastným rozvrhom (migrácia 022) sa musí správať rovnako."""

    def _rozvrh(self) -> den.Rozvrh:
        return den.Rozvrh(
            cinnosti=(
                den.Cinnost("gym", "je v posilňovni", 2.4, 60, 60, "", dni=den.VSETKY_DNI),
                den.Cinnost("home", "je doma na gauči", 0.5, 200, 200, "", dni=den.VSETKY_DNI),
            ),
            noc=den.Cinnost("bedroom", "leží v posteli", 0.6, 0, 0, "", dni=den.VSETKY_DNI),
        )

    def test_sedi_aj_s_nastavenym_dnom(self):
        dnes = date(2026, 8, 24)
        rozvrh = self._rozvrh()
        bloky = zapisane(dnes, rozvrh)
        for minuta in range(0, 1440, 11):
            teraz = datetime(dnes.year, dnes.month, dnes.day, minuta // 60, minuta % 60)
            bezi = den.block_at(teraz, SEED, rozvrh)
            zapis = v_plane(bloky, minuta)
            assert (bezi is None) == (zapis is None), f"minúta {minuta}"
            if bezi is not None:
                assert bezi.co == zapis["co"], f"minúta {minuta}"
