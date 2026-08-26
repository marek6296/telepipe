"""Nočný zámok nesmie prežiť otvorenie aktívneho okna.

STALO SA TO NAOSTRO. Simona povedala o 01:28 „im crashing", čím sa uspala do
otvorenia okna — vtedy 12:12. Klient o 09:28 prestavil začiatok na 10:06.
Fanúšik napísal o 10:39 a odpoveď mu čakala do 12:12, hoci okno bolo otvorené
už pol druha hodiny. Zámok je totiž ABSOLÚTNY čas vypočítaný z nastavenia,
ktoré sa medzitým zmenilo.
"""
from datetime import datetime

import behavior as bhv


def _cas(h, m=0):
    return datetime(2026, 8, 24, h, m)


# Okno 10:06 → 02:30, ako ho má Simona po prestavení.
OD, DO = 606, 150


class TestNocnyZamok:
    def test_v_okne_uz_neplati(self):
        """O 10:39 je okno otvorené — zámok do 12:12 stráca zmysel."""
        assert bhv.sleep_lock_expired("sleep", _cas(10, 39), OD, DO)

    def test_mimo_okna_plati_dalej(self):
        """O 08:00 ešte spí a zámok má držať."""
        assert not bhv.sleep_lock_expired("sleep", _cas(8, 0), OD, DO)

    def test_po_polnoci_zamok_DRZI(self):
        """Po polnoci nie je ráno — je to chvost VČERAJŠIEHO večera.

        Tento test pôvodne tvrdil opak a bola to chyba: okno 10:06–02:30 je
        o 01:00 síce otvorené, ale nočný zámok práve vtedy vzniká. Naostro
        povedala o 01:21 „im heading to sleep night talk tomorrow" a o 01:41
        pokračovala v rozhovore, akoby nič — lebo zámok sa pustil v tej istej
        minúte, v ktorej sa nastavil.
        """
        assert not bhv.sleep_lock_expired("sleep", _cas(1, 0), OD, DO)
        assert not bhv.sleep_lock_expired("sleep", _cas(2, 29), OD, DO)

    def test_rano_sa_zamok_pusti(self):
        """To, kvôli čomu funkcia vznikla: klient posunul otvorenie okna na
        skoršie a starý absolútny čas držal fanúšika čakať do 12:12."""
        assert bhv.sleep_lock_expired("sleep", _cas(10, 6), OD, DO)
        assert bhv.sleep_lock_expired("sleep", _cas(23, 0), OD, DO)

    def test_medzi_02_30_a_10_06_drzi(self):
        assert not bhv.sleep_lock_expired("sleep", _cas(4, 0), OD, DO)


class TestNahodneOdlozenieOstava:
    """`defer` je „ozvem sa o dve hodiny" vnútri dňa — to má platiť presne."""

    def test_v_okne_plati(self):
        assert not bhv.sleep_lock_expired("defer", _cas(14, 0), OD, DO)

    def test_mimo_okna_plati(self):
        assert not bhv.sleep_lock_expired("defer", _cas(5, 0), OD, DO)


class TestStareRiadky:
    """`None` = riadok spred rozlíšenia. Berie sa tolerantne ako nočný zámok.

    Horšie než jedno predčasne vypršané odloženie je fanúšik, ktorý čaká od rána
    — presne ten prípad, kvôli ktorému toto vzniklo.
    """

    def test_v_okne_sa_pusti(self):
        assert bhv.sleep_lock_expired(None, _cas(11, 0), OD, DO)

    def test_mimo_okna_drzi(self):
        assert not bhv.sleep_lock_expired(None, _cas(6, 0), OD, DO)


class TestNepretrzitaModelka:
    """Okno 0–0 znamená 24/7. Nočný zámok tam nevzniká, ale keby vznikol,
    nesmie držať navždy."""

    def test_vzdy_v_okne(self):
        assert bhv.sleep_lock_expired("sleep", _cas(3, 0), 0, 0)

    def test_defer_drzi_aj_tam(self):
        assert not bhv.sleep_lock_expired("defer", _cas(3, 0), 0, 0)
