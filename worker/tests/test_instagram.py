"""Instagram agent — a hlavne to, čo tam NESMIE odísť.

Na Instagrame je odkaz na stránku pre dospelých a explicitný obsah dôvod na
zrušenie účtu, a účet je jediné, čo modelka naozaj má. Tieto testy nie sú
o kvalite odpovede, ale o tom, že sa hranica nedá prekročiť ani omylom.
"""
from datetime import datetime, timedelta, timezone

import instagram_api as api
import instagram_pravidla as pravidla


class TestOrezavanie:
    """Instagram meria text v BAJTOCH, nie v znakoch."""

    def test_kratky_text_ostava(self):
        assert api.orez("hey you 😄") == "hey you 😄"

    def test_dlhy_text_sa_skrati(self):
        out = api.orez("a" * 1500)
        assert len(out.encode("utf-8")) <= api.MAX_BAJTOV

    def test_emoji_sa_ratajú_ako_styri_bajty(self):
        """Tisíc emoji je štyritisíc bajtov — počítanie znakov by bola tichá chyba."""
        out = api.orez("😄" * 400)
        assert len(out.encode("utf-8")) <= api.MAX_BAJTOV

    def test_nereze_uprostred_znaku(self):
        out = api.orez("😄" * 400)
        out.encode("utf-8").decode("utf-8")  # nesmie hodiť

    def test_reze_na_hranici_slova(self):
        veta = ("slovo " * 400).strip()
        out = api.orez(veta)
        assert not out.endswith("slov"), "nemá končiť rozseknutým slovom"

    def test_prazdny_text(self):
        assert api.orez("   ") == ""


class TestOkno:
    """Po 24 hodinách Instagram odpoveď odmietne."""

    def test_cerstva_sprava(self):
        pred_hodinou = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert api.v_okne(pred_hodinou)

    def test_stara_sprava(self):
        pred_dvoma_dnami = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        assert not api.v_okne(pred_dvoma_dnami)

    def test_tesne_pred_koncom(self):
        skoro = (datetime.now(timezone.utc) - timedelta(hours=23, minutes=50)).isoformat()
        assert api.v_okne(skoro)

    def test_bez_casu_sa_neodpisuje(self):
        """Pri pochybnosti radšej mlčať — odpoveď po okne Instagram odmietne."""
        assert not api.v_okne(None)
        assert not api.v_okne("toto nie je dátum")


class TestRozobranieKonverzacie:
    MOJE = "17841400000000000"

    def _konv(self, spravy):
        return {
            "id": "conv-1",
            "updated_time": "2026-08-24T10:00:00+0000",
            "messages": {"data": spravy},
        }

    def test_pozna_kto_je_kto(self):
        chat = api.rozober(
            self._konv([
                {"id": "m2", "from": {"id": self.MOJE}, "message": "hey you"},
                {"id": "m1", "from": {"id": "999", "username": "fan"}, "message": "hi"},
            ]),
            self.MOJE,
        )
        assert chat["igsid"] == "999"
        assert chat["username"] == "fan"
        assert [s["role"] for s in chat["spravy"]] == ["user", "assistant"]

    def test_spravy_su_od_najstarsej(self):
        """Instagram ich dáva od najnovšej, prompt ich potrebuje naopak."""
        chat = api.rozober(
            self._konv([
                {"id": "m3", "from": {"id": "999"}, "message": "tretia"},
                {"id": "m2", "from": {"id": "999"}, "message": "druha"},
                {"id": "m1", "from": {"id": "999"}, "message": "prva"},
            ]),
            self.MOJE,
        )
        assert [s["content"] for s in chat["spravy"]] == ["prva", "druha", "tretia"]

    def test_fotka_bez_textu_ostane_v_historii(self):
        """Inak modelka odpovie do prázdna — jeho ťah tam musí byť."""
        chat = api.rozober(
            self._konv([{"id": "m1", "from": {"id": "999"}, "message": ""}]),
            self.MOJE,
        )
        assert chat["spravy"][0]["content"] == "[poslal médium bez textu]"

    def test_moja_prazdna_sprava_sa_zahodi(self):
        chat = api.rozober(
            self._konv([{"id": "m1", "from": {"id": self.MOJE}, "message": ""}]),
            self.MOJE,
        )
        assert chat["spravy"] == []

    def test_igsid_z_ucastnikov_ked_v_spravach_nie_je(self):
        konv = self._konv([{"id": "m1", "from": {"id": self.MOJE}, "message": "ahoj"}])
        konv["participants"] = {"data": [{"id": self.MOJE}, {"id": "999", "username": "fan"}]}
        chat = api.rozober(konv, self.MOJE)
        assert chat["igsid"] == "999"


class TestPravidlaChraniaUcet:
    """Toto sú tie zákazy, kvôli ktorým celá vrstva existuje."""

    NASTAVENIA = {"funnel_target": "telegram", "telegram_handle": "simona_here"}

    def test_zakazuje_platene_platformy(self):
        blok = pravidla.blok(self.NASTAVENIA)
        assert "Fanvue" in blok and "OnlyFans" in blok
        assert "NIKDY nespomeň" in blok

    def test_zakazuje_explicitny_obsah(self):
        assert "Žiadny explicitný obsah" in pravidla.blok(self.NASTAVENIA)

    def test_zakazuje_media(self):
        blok = pravidla.blok(self.NASTAVENIA)
        assert "fotky" in blok and "hlasovky" in blok

    def test_zakazuje_odkazy(self):
        assert "Neposielaj žiadne odkazy" in pravidla.blok(self.NASTAVENIA)

    def test_telegram_meno_ide_slovami_nie_ako_odkaz(self):
        blok = pravidla.blok(self.NASTAVENIA)
        assert "simona_here" in blok
        assert "t.me" in blok and "nikdy ako odkaz" in blok

    def test_odkaz_v_biu_neposiela_adresu(self):
        blok = pravidla.blok({"funnel_target": "bio_link", "bio_link": "https://linkovne.com/x"})
        assert "NIKDY nepíš samotnú adresu" in blok
        assert "linkovne.com" not in blok, "adresa sa do promptu nedostane"

    def test_bez_ciela_nepozyva_nikam(self):
        """Klient cieľ nedoplnil — radšej ticho než vymyslená adresa."""
        blok = pravidla.blok({"funnel_target": "telegram", "telegram_handle": ""})
        assert "Nikam" in blok


class TestKolkoRazPozyva:
    def test_prvy_raz_smie(self):
        assert pravidla.smie_pozvat({"pointed_count": 0}, 5)

    def test_hned_po_prvom_nie(self):
        """Bez odstupu by to zopakovala v ďalšej odpovedi."""
        assert not pravidla.smie_pozvat({"pointed_count": 1}, 3)

    def test_po_dostatocnom_odstupe_ano(self):
        assert pravidla.smie_pozvat({"pointed_count": 1}, 12)

    def test_po_strope_uz_nikdy(self):
        assert not pravidla.smie_pozvat({"pointed_count": pravidla.MAX_POZVANI}, 500)

    def test_strop_je_nizky(self):
        """Opakované pozývanie vyzerá ako rozposielanie a to si Instagram všíma."""
        assert pravidla.MAX_POZVANI <= 2


class TestRozhranieDb:
    """Vie `TenantInstagramDb` všetko, čo od nej agent pýta?

    Presne táto chyba dnes zhodila Fanvue vetvu na vyše dňa: do agenta pribudlo
    volanie, ktorá trieda nemala, a kolo padalo na `AttributeError`. Fake objekty
    v testoch to nechytia — majú presne tie metódy, ktoré si test doplní.
    """

    def test_agent_nevola_nic_co_db_nema(self):
        import re
        from pathlib import Path

        import instagram_tenant

        src = Path(__file__).resolve().parents[1] / "src" / "instagram_agent.py"
        volania = set(re.findall(r"self\._db\.([a-z_][a-z0-9_]*)\(", src.read_text("utf-8")))
        ma = {m for m in dir(instagram_tenant.TenantInstagramDb) if not m.startswith("__")}
        chyba = volania - ma
        assert not chyba, f"agent volá metódy, ktoré TenantInstagramDb nemá: {sorted(chyba)}"

    def test_test_naozaj_nieco_kontroluje(self):
        import re
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "src" / "instagram_agent.py"
        volania = set(re.findall(r"self\._db\.([a-z_][a-z0-9_]*)\(", src.read_text("utf-8")))
        assert len(volania) >= 6, f"našlo sa len {len(volania)} volaní — regex asi prestal sedieť"


class TestVrstvaJeNadPersonou:
    """Instagram pravidlá musia byť POSLEDNÉ — inak ich persona prebije."""

    def test_agent_pripaja_pravidla_za_prompt(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "instagram_agent.py").read_text("utf-8")
        assert "system += " in src, "pravidlá sa musia pripájať ZA hotový prompt"
        assert "allow_link=False" in src, "odkaz na platenú platformu tu nesmie byť povolený nikdy"
