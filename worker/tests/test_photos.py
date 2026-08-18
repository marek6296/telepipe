"""Fotky na pevné albumy — album podľa miesta, raz za chat, nikdy tá istá dvakrát."""
import random
from datetime import datetime, timedelta, timezone

import photos as P

TERAZ = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


def foto(id, folder, spicy=False, active=True):
    return {"id": id, "folder": folder, "spicy": spicy, "active": active, "caption": "x"}


def user(msg_count=16, last_photo_at=None, tg_id=555):
    return {"tg_id": tg_id, "msg_count": msg_count, "last_photo_at": last_photo_at}


class TestFolderFor:
    def test_gym(self):
        assert P.folder_for("gym", 10) == "gym"

    def test_domov(self):
        for miesto in ("home", "kitchen", "bathroom"):
            assert P.folder_for(miesto, 12) == "home"

    def test_mesto(self):
        for miesto in ("outside", "cafe", "car"):
            assert P.folder_for(miesto, 12) == "city"

    def test_postel_rano_vs_noc(self):
        assert P.folder_for("bedroom", 8) == "bed_morning"
        assert P.folder_for("bedroom", 22) == "bed_night"
        assert P.folder_for("bedroom", 2) == "bed_night"

    def test_nic_nesedi_univerzal(self):
        assert P.folder_for("none", 12) == "universal"
        assert P.folder_for("", 12) == "universal"


class TestSendReason:
    def test_vypytal_si(self):
        assert P.send_reason("send me a pic", user()) == "asked"

    def test_pochybuje_ale_uz_videl(self):
        u = user(last_photo_at=TERAZ.isoformat())
        assert P.send_reason("are you a bot?", u) == "proof"

    def test_pochybuje_ale_este_nevidel_nic(self):
        # Pochybnosť bez predošlej fotky a pred prahom prvej selfie → nič.
        assert P.send_reason("are you real?", user(msg_count=4, last_photo_at=None)) is None

    def test_prva_selfie_v_okne_10_20(self):
        assert P.send_reason("cool", user(msg_count=16)) == "first"

    def test_prva_selfie_prilis_skoro(self):
        assert P.send_reason("cool", user(msg_count=4)) is None

    def test_po_prvej_uz_nic_sama_od_seba(self):
        """Keď už fotka odišla, sama od seba viac neposiela — len na vyžiadanie."""
        u = user(msg_count=40, last_photo_at=TERAZ.isoformat())
        assert P.send_reason("nice weather", u) is None


class TestPick:
    LIB = [foto(1, "gym"), foto(2, "gym"), foto(3, "home"), foto(4, "universal")]

    def test_posle_z_albumu_podla_miesta(self):
        p = P.pick(self.LIB, [], "gym", "first")
        assert p["folder"] == "gym"

    def test_prva_z_miesta_nesedi_padne_na_univerzal(self):
        # V gyme nič (album prázdny) → univerzál.
        lib = [foto(4, "universal")]
        p = P.pick(lib, [], "gym", "first")
        assert p["folder"] == "universal"

    def test_album_sa_pouzije_len_raz(self):
        # Fotka 1 z gymu už odišla → gym je „použitý", ďalšia z gymu nejde
        # ani keď je voľná; ide iný nepoužitý album.
        p = P.pick(self.LIB, [1], "gym", "first")
        assert p["folder"] != "gym"

    def test_first_nesiaha_po_cudzom_albume(self):
        # Sama od seba: keď miesto (gym) je použité a univerzál tiež, radšej nič.
        lib = [foto(1, "gym"), foto(4, "universal")]
        assert P.pick(lib, [1, 4], "gym", "first") is None

    def test_asked_siahne_aj_po_inom_albume(self):
        # Vypýtal si → keď gym aj univerzál nesedia, vezme hociktorý nepoužitý.
        lib = [foto(3, "home")]
        p = P.pick(lib, [], "gym", "asked")
        assert p["folder"] == "home"

    def test_okno_pusti_druhu_z_toho_isteho(self):
        # V 30-min okne + vypýtal si → druhá z otvoreného albumu.
        p = P.pick(self.LIB, [1], "home", "asked", open_folder="gym", can_reopen=True)
        assert p["id"] == 2 and p["folder"] == "gym"

    def test_bez_okna_druha_z_toho_isteho_nejde(self):
        # Okno zavreté → gym je použitý, druhá nejde; ide iný album.
        p = P.pick(self.LIB, [1], "gym", "asked", open_folder="gym", can_reopen=False)
        assert p["folder"] != "gym"

    def test_nikdy_uz_videnu(self):
        p = P.pick([foto(1, "gym")], [1], "gym", "asked")
        assert p is None

    def test_prefer_spicy(self):
        lib = [foto(1, "gym", spicy=False), foto(2, "gym", spicy=True)]
        p = P.pick(lib, [], "gym", "asked", prefer_spicy=True)
        assert p["id"] == 2


class TestPomocne:
    LIB = [foto(1, "gym"), foto(2, "home"), foto(3, "gym")]

    def test_used_folders(self):
        assert P.used_folders(self.LIB, [1]) == {"gym"}
        assert P.used_folders(self.LIB, [1, 2]) == {"gym", "home"}

    def test_last_folder(self):
        # sent_ids je od najnovšej — [2, 1] znamená posledná bola fotka 2 (home).
        assert P.last_folder(self.LIB, [2, 1]) == "home"
        assert P.last_folder(self.LIB, []) is None

    def test_window_open(self):
        cerstva = user(last_photo_at=(TERAZ - timedelta(minutes=10)).isoformat())
        stara = user(last_photo_at=(TERAZ - timedelta(minutes=40)).isoformat())
        assert P.window_open(cerstva, TERAZ)
        assert not P.window_open(stara, TERAZ)
        assert not P.window_open(user(last_photo_at=None), TERAZ)


class TestCooldown:
    def test_bez_predoslej_prejde(self):
        assert P.cooldown_passed(user(last_photo_at=None), 45)

    def test_nedavnu_zablokuje(self):
        u = user(last_photo_at=(TERAZ - timedelta(minutes=10)).isoformat())
        assert not P.cooldown_passed(u, 45, now=TERAZ)

    def test_po_case_prejde(self):
        u = user(last_photo_at=(TERAZ - timedelta(minutes=60)).isoformat())
        assert P.cooldown_passed(u, 45, now=TERAZ)


def test_remaining():
    lib = [foto(1, "gym"), foto(2, "home"), foto(3, "city", active=False)]
    assert P.remaining(lib, []) == 2  # neaktívna sa neráta
    assert P.remaining(lib, [1]) == 1
