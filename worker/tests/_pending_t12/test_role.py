"""Rola služby — ktorý program sa na Railway naozaj spustí.

Všetky služby zdieľajú jeden štartovací príkaz, takže o role rozhoduje
premenná. Keby sa pomýlila, bežal by druhý userbot na tej istej Telegram
session a zneplatnil by ju.
"""
from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"


def _main_source() -> str:
    return (SRC / "main.py").read_text(encoding="utf-8")


class TestRozhodovanie:
    def test_main_pozna_premennu_role(self):
        assert 'SERVICE_ROLE' in _main_source()

    def test_fanvue_rola_spusta_agenta(self):
        source = _main_source()
        assert "from main_fanvue import run as run_fanvue" in source
        assert "run_fanvue()" in source

    def test_telegram_ostava_predvolena(self):
        """Bez premennej sa musí správať presne ako doteraz."""
        source = _main_source()
        assert 'os.getenv("SERVICE_ROLE", "")' in source

    def test_oba_vstupne_body_su_platny_python(self):
        for name in ("main.py", "main_fanvue.py"):
            ast.parse((SRC / name).read_text(encoding="utf-8"))


class TestStartovaciPrikaz:
    def test_railway_json_spusta_main(self):
        import json

        root = SRC.parent
        config = json.loads((root / "railway.json").read_text(encoding="utf-8"))
        assert config["deploy"]["startCommand"] == "python src/main.py"
