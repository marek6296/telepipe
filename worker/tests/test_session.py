"""Krivka pozornosti — na 40. správe nesmie byť rovnako svieža ako na prvej."""
from datetime import datetime, timedelta, timezone

import memory

TERAZ = datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc)


def chat(*hodin_dozadu):
    return [{"created_at": (TERAZ - timedelta(hours=h)).isoformat()} for h in hodin_dozadu]


class TestDlzkaSedenia:
    def test_cerstvy_rozhovor(self):
        assert memory.session_hours(chat(0.3, 0.1), TERAZ) < 0.5

    def test_pocita_od_zaciatku_sedenia(self):
        assert 2.4 < memory.session_hours(chat(2.5, 2.0, 0.1), TERAZ) < 2.6

    def test_dlha_pauza_zacina_nove_sedenie(self):
        """Včerajšie správy sa do dnešného sedenia nerátajú."""
        assert memory.session_hours(chat(30, 29, 2.5, 2.0, 0.1), TERAZ) < 2.6

    def test_prazdna_historia(self):
        assert memory.session_hours([], TERAZ) == 0.0

    def test_rozbity_cas_nezhodi(self):
        assert memory.session_hours([{"created_at": "nezmysel"}], TERAZ) == 0.0
