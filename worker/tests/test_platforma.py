"""Kam modelka ťahá ľudí — Fanvue alebo OnlyFans.

Najdôležitejšie tvrdenie tohto testu: prepnutie platformy NESMIE zmeniť logiku
funnelu. Mení sa jediné — ako sa tá stránka volá, keď sa jej na ňu spýtajú.
"""
from persona import build_system_prompt, nazov_platformy


def _prompt(platform=None, **kw):
    persona = {
        "name": "Simona", "language": "", "languages": "",
        "lang_primary": "en", "lang_extra": [],
        "backstory": "", "tone": "", "msg_style": "", "boundaries": "",
        "funnel_rules": "SEND-THEM-THERE", "cta_link": "https://x.example/s",
        "extra_rules": "", "examples": "",
    }
    if platform is not None:
        persona["platform"] = platform
    persona.update(kw.pop("persona", {}))
    return build_system_prompt(
        persona, {"tg_id": 1, "msg_count": 30, "funnel_stage": "warm"},
        allow_link=True, asked_if_ai=False, **kw,
    )


class TestPomenovanie:
    def test_default_je_fanvue(self):
        """Modelky spred tejto zmeny nemajú stĺpec — nesmú stratiť meno stránky."""
        assert nazov_platformy({}) == "Fanvue"
        assert "Fanvue" in _prompt()

    def test_onlyfans_sa_pomenuje_spravne(self):
        out = _prompt("onlyfans")
        assert "OnlyFans" in out
        assert "Fanvue" not in out

    def test_fanvue_nespomina_onlyfans(self):
        out = _prompt("fanvue")
        assert "Fanvue" in out
        assert "OnlyFans" not in out

    def test_other_nepomenuje_nic(self):
        """Kto má stránku inde, nemá o nej klamať ani ju menovať."""
        out = _prompt("other")
        assert "OnlyFans" not in out
        assert "AKO SA VOLÁ TVOJA STRÁNKA" not in out

    def test_neznama_hodnota_nepomenuje(self):
        assert nazov_platformy({"platform": "myspace"}) == ""

    def test_nevymysla_si_ucty(self):
        """Na otázku o konkurenčnej platforme má povedať, že tam nie je."""
        out = _prompt("onlyfans")
        assert "Nevymýšľaj si účty" in out


class TestLogikaSaNemeni:
    """Toto je to, čo sa nesmelo pokaziť."""

    def test_funnel_pravidla_su_rovnake_pre_obe(self):
        fan = _prompt("fanvue")
        of = _prompt("onlyfans")
        # Klientove funnel pravidlá idú do promptu rovnako.
        assert "SEND-THEM-THERE" in fan and "SEND-THEM-THERE" in of

    def test_rozdiel_je_iba_v_pomenovani(self):
        """Prompty sa smú líšiť LEN v tej jednej sekcii o názve stránky."""
        fan = set(_prompt("fanvue").split("\n\n"))
        of = set(_prompt("onlyfans").split("\n\n"))
        rozdiel = fan.symmetric_difference(of)
        assert all("STRÁNKA" in blok.upper() for blok in rozdiel), rozdiel
