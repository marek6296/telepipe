"""Porovnávanie významu — na tomto stojí celé odstránenie parafráz z pamäte."""
import similar


class TestParafrazyZoZivychDat:
    """Presne tie dvojice, ktoré naživo ležali v databáze vedľa seba."""

    DVOJICE = [
        ("má tetovanie", "je tetovaná"),
        ("žije sama", "býva sama"),
        ("má stránku na Fanvue", "má Fanvue stránku sima.sima"),
        ("bývala pri jazere", "má staré bydlisko pri jazere"),
        ("nerobí videohovory, len fotky a chaty", "nerobí video hovory"),
        ("má stránku, kde dáva voice a hot content",
         "má stránku, kde necháva voice a hot content"),
        ("used to live in Sacramento, Auburn and South Lake Tahoe",
         "used to live in Sacramento, Auburn and South Lake Tahoe"),
        ("uses power washer, needs new hose because it broke",
         "usually uses power washer; needs new hose because it broke"),
        ("wants extreme loyalty shown through actions",
         "extremely loyal partner who shows it through actions"),
    ]

    def test_su_to_tie_iste_veci(self):
        for a, b in self.DVOJICE:
            assert similar.same_idea(a, b), f"malo sa zhodnúť: {a!r} vs {b!r}"


class TestRozneVeciSaNezluciaa:
    ROZNE = [
        ("počúva rock", "počúva rap"),
        ("má psa", "má mačku"),
        ("pracuje ako vodič kamiónu", "má dve deti"),
        ("býva v Kalifornii", "býva v Michigane"),
        ("má rád ráno", "nemá rád ráno"),
    ]

    def test_ostanu_oddelene(self):
        for a, b in self.ROZNE:
            assert not similar.same_idea(a, b), f"nemalo sa zhodnúť: {a!r} vs {b!r}"

    def test_negacia_nikdy_nie_je_zhoda(self):
        assert not similar.same_idea("robí videohovory", "nerobí videohovory")

    def test_prazdne_nie_su_zhoda(self):
        assert not similar.same_idea("", "")
        assert not similar.same_idea("má psa", "")


class TestDedupe:
    def test_z_kazdej_skupiny_ostane_prva(self):
        out = similar.dedupe(
            ["žije sama", "býva sama", "počúva rock", "má vlastný byt a žije sama"]
        )
        assert out[0] == "žije sama"
        assert "počúva rock" in out
        assert len(out) == 2

    def test_zachova_poradie(self):
        out = similar.dedupe(["prvá vec tu", "druhá iná vec", "tretia úplne iná"])
        assert out == ["prvá vec tu", "druhá iná vec", "tretia úplne iná"]

    def test_prazdne_riadky_vypadnu(self):
        assert similar.dedupe(["", "   ", "má psa"]) == ["má psa"]


class TestIsNew:
    def test_parafraza_nie_je_nova(self):
        assert not similar.is_new("je tetovaná", ["má tetovanie", "žije sama"])

    def test_naozaj_nova_prejde(self):
        assert similar.is_new("má brata v Texase", ["má tetovanie", "žije sama"])
