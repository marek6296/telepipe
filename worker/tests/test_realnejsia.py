"""Tri opravy z rozboru skutočných konverzácií (21.–23. 8.).

Každá vychádza z niečoho, čo sa naozaj stalo, nie z dojmu — čísla sú
v komentároch pri jednotlivých triedach.
"""
import humanize
import taper


class TestOdkazSaNeverModelu:
    """Z troch odoslaných odkazov odišiel jeden ako „://telepipe.me/r/…".

    Prešlo to len šťastím: Telegram si odkaz spravil aj z holej domény. Keby
    model pokazil znak v tokene, fanúšik skončí na úvodnej stránke a klik sa
    nezaráta nikomu — teda presne to, čo má meranie zisťovať.
    """

    SPRAVNY = "https://telepipe.me/r/LpmwAUkF"

    def test_chybajuca_schema(self):
        """Presne ten prípad z produkcie."""
        out = humanize.repair_link(
            "im freer on my page ://telepipe.me/r/LpmwAUkF", self.SPRAVNY
        )
        assert out == "im freer on my page https://telepipe.me/r/LpmwAUkF"

    def test_hola_domena(self):
        out = humanize.repair_link("find me here telepipe.me/r/LpmwAUkF ok?", self.SPRAVNY)
        assert self.SPRAVNY in out and out.endswith("ok?")

    def test_preklep_v_tokene(self):
        """Zlý token je horší než žiadny odkaz — vedie na úvodnú stránku."""
        out = humanize.repair_link("here https://telepipe.me/r/LpmwAUkX babe", self.SPRAVNY)
        assert out == f"here {self.SPRAVNY} babe"

    def test_http_namiesto_https(self):
        assert humanize.repair_link("here http://telepipe.me/r/x", self.SPRAVNY).endswith(
            self.SPRAVNY
        )

    def test_spravny_odkaz_ostava_nedotknuty(self):
        text = f"here {self.SPRAVNY}"
        assert humanize.repair_link(text, self.SPRAVNY) == text

    def test_bodka_na_konci_vety_ostava(self):
        out = humanize.repair_link("go to www.telepipe.me/r/x.", self.SPRAVNY)
        assert out == f"go to {self.SPRAVNY}."

    def test_dvojbodka_pred_adresou_sa_nezlepi(self):
        out = humanize.repair_link("napis mi sem: telepipe.me/r/x", self.SPRAVNY)
        assert out == f"napis mi sem: {self.SPRAVNY}"

    def test_text_bez_odkazu_sa_nemeni(self):
        assert humanize.repair_link("nothing here babe", self.SPRAVNY) == "nothing here babe"

    def test_bez_spravneho_odkazu_sa_nehada(self):
        text = "here telepipe.me/r/whatever"
        assert humanize.repair_link(text, "") == text


class TestCitoslovciaSaRataju_Spolu:
    """V jednom chate začínalo citoslovcom 31 z 85 správ (36 %) a pôvodné
    pravidlo z nich nestrhlo ANI JEDNO — lebo sa striedali:
    „aw" 26 %, „haha" 23 %, „lol" 11 %, „hehe" 8 %.
    """

    def _historia(self, vzor):
        """`vzor` = napr. 'aw haha lol hehe' → história začínajúca tými slovami."""
        return [f"{w} nieco k tomu" for w in vzor.split()]

    def test_striedanie_citosloviec_sa_uz_chyti(self):
        out = humanize.thin_openers(
            "aw to je milé", self._historia("haha lol hehe aw haha lol")
        )
        assert not out.startswith("aw")
        assert "to je milé" in out

    def test_obcasne_citoslovce_ostava(self):
        text = "haha to je dobre"
        historia = self._historia("yeah just ok im nice") + ["haha raz"]
        assert humanize.thin_openers(text, historia) == text

    def test_ine_slovo_sa_neriesi(self):
        """Pravidlo je o citoslovciach, nie o každom opakovaní."""
        text = "just chilling at home"
        assert humanize.thin_openers(text, self._historia("aw haha lol hehe aw")) == text

    def test_kratka_historia_nestaci(self):
        text = "aw ty si zlaty"
        assert humanize.thin_openers(text, self._historia("aw haha")) == text

    def test_nezostane_prazdna_sprava(self):
        assert humanize.thin_openers("aw", self._historia("aw haha lol hehe aw")) == "aw"


class TestUtlmSaNelucii:
    """Fanúšik dostal 22. 8. o 16:29 „im mostly on my fanvue, come find me",
    potom si s ňou hodinu normálne písal a rozlúčka prišla až na druhý deň.
    Text úrovne 3 vznikol v čase, keď rozlúčka ešte neexistovala.
    """

    def test_uroven_tri_neoznamuje_odchod(self):
        text = taper.GUIDANCE[3]
        assert "NEOZNAMUJ" in text
        assert "už nebývaš" in text, "má to byť výslovne zakázané, nie len vynechané"

    def test_uroven_tri_nekaze_povedat_ze_je_inde(self):
        assert "POVEDZ MU TO" not in taper.GUIDANCE[3]

    def test_stranka_sa_smie_spomenut(self):
        """Zakazuje sa lúčenie, nie funnel."""
        assert "stránke" in taper.GUIDANCE[3] or "stránku" in taper.GUIDANCE[3]

    def test_ostatne_urovne_ostali(self):
        for uroven in (1, 2, 4):
            assert taper.GUIDANCE[uroven].startswith("ÚTLM")


class TestNameraneNaSkutocnychSpravach:
    """Poistka na hranicu: keby ju niekto zdvihol, tik sa ticho vráti."""

    def test_hranica_ostava_nizka(self):
        assert humanize.VYPLNKOVY_PODIEL <= 0.2, (
            "nad 0.2 sa pravidlo ustáli nad 25 % a to je späť tam, kde sme začali"
        )

    def test_striedanie_troch_roznych_sa_chyti(self):
        """Presne vzor z produkcie: aw → haha → lol → hehe dokola."""
        historia = ["aw a", "haha b", "lol c", "hehe d", "yeah e", "just f"]
        out = humanize.thin_openers("aw znova", historia)
        assert not out.startswith("aw")

    def test_bezne_pisanie_bez_citosloviec_sa_nedotkne(self):
        historia = ["just chilling", "im home", "yeah true", "not really", "sounds fun"]
        for text in ("aw thats sweet", "haha ok"):
            assert humanize.thin_openers(text, historia) == text
