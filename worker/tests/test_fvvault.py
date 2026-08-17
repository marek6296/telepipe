"""Načítanie vaultu na požiadanie z dashboardu.

Dve veci, na ktorých to stojí:

**Naše stĺpce sú nedotknuteľné.** Popis, cena, vypínač a počet odoslaní vo
vaulte neexistujú — sú to jediné informácie, ktoré o fotke máme len my. Keby ich
synchronizácia prepísala, Marek by po jednom kliknutí prišiel o celé nastavenie
zbierky.

**Nedokončená požiadavka je zámok.** `finished_at is null` je partial unique
index (migrácia 015), takže neuzavretá požiadavka zablokuje tlačidlo aj pre
ďalšie pokusy. Riadok sa preto dopisuje aj po zlyhaní.
"""
from __future__ import annotations

import fvvault
import pytest


def item(uuid="m1", *, kind="image", desc="ja v kuchyni", price=None, thumb="https://t/1.jpg"):
    """Položka tak, ako ju vracia `GET /media?variants=thumbnail,main`."""
    row = {"uuid": uuid, "mediaType": kind, "description": desc}
    if price is not None:
        row["recommendedPrice"] = price
    if thumb:
        row["variants"] = [{"variantType": "thumbnail", "url": thumb}]
    return row


# ---------------------------------------------------------------------------
# Náhľady
# ---------------------------------------------------------------------------


class TestNahlad:
    def test_thumbnail_ma_prednost(self):
        raw = {
            "variants": [
                {"variantType": "main", "url": "https://t/main.jpg"},
                {"variantType": "thumbnail", "url": "https://t/small.jpg"},
            ]
        }
        assert fvvault.thumb_of(raw) == "https://t/small.jpg"

    def test_bez_thumbnailu_poslúži_main(self):
        """`thumbnail` nemá vygenerovaná každá položka — inak by časť zbierky
        ostala v dashboarde bez obrázka."""
        raw = {"variants": [{"variantType": "main", "url": "https://t/main.jpg"}]}
        assert fvvault.thumb_of(raw) == "https://t/main.jpg"

    def test_ziadne_varianty_su_prazdny_retazec(self):
        assert fvvault.thumb_of({}) == ""
        assert fvvault.thumb_of({"variants": []}) == ""
        assert fvvault.thumb_of({"variants": "nezmysel"}) == ""

    def test_variant_bez_adresy_sa_preskoci(self):
        raw = {
            "variants": [
                {"variantType": "thumbnail", "url": ""},
                {"variantType": "main", "url": "https://t/main.jpg"},
            ]
        }
        assert fvvault.thumb_of(raw) == "https://t/main.jpg"


# ---------------------------------------------------------------------------
# Nová položka
# ---------------------------------------------------------------------------


class TestNovaFotka:
    def test_riadok_ma_vsetko_co_dashboard_potrebuje(self):
        row = fvvault.fresh_row(item(price=1500), "Clients NSFW")
        assert row["media_uuid"] == "m1"
        assert row["folder"] == "Clients NSFW"
        assert row["kind"] == "image"
        assert row["caption"] == "ja v kuchyni"
        assert row["price_cents"] == 1500
        assert row["thumb_url"] == "https://t/1.jpg"

    def test_bez_uuid_sa_polozka_zahodi(self):
        assert fvvault.fresh_row({"description": "nic"}, "F") is None

    def test_odporucana_cena_ma_prednost_pred_priecinkovou(self):
        row = fvvault.fresh_row(item(price=2500), "F", folder_price_cents=900)
        assert row["price_cents"] == 2500

    def test_bez_odporucanej_ceny_plati_priecinkova(self):
        """Bez ceny by fotku z plateného priečinka `fvmedia.pick(paid=True)`
        odfiltroval a nikdy by neodišla."""
        row = fvvault.fresh_row(item(), "F", folder_price_cents=900)
        assert row["price_cents"] == 900

    def test_bez_oboch_cien_je_nula(self):
        assert fvvault.fresh_row(item(), "F")["price_cents"] == 0

    def test_zaporna_priecinkova_cena_sa_nepouzije(self):
        assert fvvault.fresh_row(item(), "F", folder_price_cents=-50)["price_cents"] == 0

    def test_zvuk_z_vaultu_ostava_zvukom(self):
        """Poslať hlasovku ako fotku by odhalilo, že si obsah nikto nepozrel."""
        assert fvvault.fresh_row(item(kind="AUDIO"), "F")["kind"] == "audio"


# ---------------------------------------------------------------------------
# Známa položka — čoho sa sync smie dotknúť
# ---------------------------------------------------------------------------


class TestOsvieženie:
    KNOWN = {
        "media_uuid": "m1",
        "folder": "Clients SFW",
        "kind": "image",
        "thumb_url": "https://t/stary.jpg",
        "caption": "moje slova",
        "fits": "vecer",
        "price_cents": 700,
        "active": False,
        "spicy": True,
        "sent_count": 4,
        "posted_at": "2026-08-01T00:00:00Z",
    }

    def test_nezmenena_fotka_nevyrobi_zapis(self):
        raw = item(desc="cokolvek", thumb="https://t/stary.jpg")
        assert fvvault.refresh_patch(self.KNOWN, raw, "Clients SFW") == {}

    def test_presun_do_ineho_priecinka_sa_zachyti(self):
        patch = fvvault.refresh_patch(self.KNOWN, item(thumb="https://t/stary.jpg"), "Posts")
        assert patch == {"folder": "Posts"}

    def test_novy_nahlad_prepise_stary(self):
        patch = fvvault.refresh_patch(self.KNOWN, item(thumb="https://t/novy.jpg"), "Clients SFW")
        assert patch == {"thumb_url": "https://t/novy.jpg"}

    def test_prazdny_nahlad_stary_nezmaze(self):
        """Fanvue ho občas nevráti — stará adresa je lepšia než žiadna."""
        patch = fvvault.refresh_patch(self.KNOWN, item(thumb=""), "Clients SFW")
        assert "thumb_url" not in patch

    @pytest.mark.parametrize(
        "field", ["caption", "fits", "price_cents", "active", "spicy", "sent_count", "posted_at"]
    )
    def test_nase_stlpce_sync_nikdy_neprepise(self, field):
        raw = item(desc="popis z fanvue", price=9999, thumb="https://t/novy.jpg")
        assert field not in fvvault.refresh_patch(self.KNOWN, raw, "Posts")

    def test_polozka_bez_uuid_nevyrobi_patch(self):
        assert fvvault.refresh_patch(self.KNOWN, {"description": "x"}, "F") == {}


# ---------------------------------------------------------------------------
# Celé kolo
# ---------------------------------------------------------------------------


class FakeApi:
    def __init__(self, folders, media):
        self.folders_rows = folders
        self.media_rows = media
        self.asked = []

    async def vault_folders(self, creator_uuid):
        self.asked.append(creator_uuid)
        return self.folders_rows

    async def folder_media(self, folder):
        return self.media_rows.get(folder, [])


class FakeDb:
    def __init__(self, folders=None, media=None):
        self._folders = folders or []
        self._media = media or []
        self.saved_folders = []
        self.upserted = []
        self.updated = []
        self.synced = 0

    async def folders(self):
        return list(self._folders)

    async def all_media(self):
        return list(self._media)

    async def save_folder(self, name, patch):
        self.saved_folders.append((name, patch))

    async def upsert_media(self, rows):
        self.upserted.extend(rows)

    async def update_media(self, uuid, patch):
        self.updated.append((uuid, patch))

    async def mark_vault_synced(self):
        self.synced += 1


class TestKolo:
    async def test_nove_fotky_pribudnu_a_priecinky_sa_spocitaju(self):
        api = FakeApi(
            [{"name": "Posts"}, {"name": "Clients NSFW"}],
            {"Posts": [item("a")], "Clients NSFW": [item("b"), item("c")]},
        )
        db = FakeDb()
        out = await fvvault.run_once(db, api, "creator-1")
        assert out == {"folders": 2, "media_new": 3, "media_seen": 3}
        assert {u for u, _ in db.saved_folders} == {"Posts", "Clients NSFW"}
        assert dict(db.saved_folders)["Clients NSFW"] == {"media_count": 2}
        assert {r["media_uuid"] for r in db.upserted} == {"a", "b", "c"}
        assert db.synced == 1

    async def test_znama_fotka_sa_nevklada_druhy_raz(self):
        api = FakeApi([{"name": "Posts"}], {"Posts": [item("a", thumb="https://t/1.jpg")]})
        db = FakeDb(media=[{"media_uuid": "a", "folder": "Posts", "kind": "image",
                            "thumb_url": "https://t/1.jpg", "caption": "moje"}])
        out = await fvvault.run_once(db, api, "creator-1")
        assert out["media_new"] == 0 and out["media_seen"] == 1
        assert db.upserted == [] and db.updated == []

    async def test_priecinkova_cena_sa_pouzije_na_nove_fotky(self):
        api = FakeApi([{"name": "Clients NSFW"}], {"Clients NSFW": [item("a")]})
        db = FakeDb(folders=[{"name": "Clients NSFW", "role": "nsfw", "price_cents": 1200}])
        await fvvault.run_once(db, api, "creator-1")
        assert db.upserted[0]["price_cents"] == 1200

    async def test_priecinok_bez_mena_sa_preskoci(self):
        api = FakeApi([{"name": ""}, {"name": "Posts"}], {"Posts": []})
        db = FakeDb()
        assert (await fvvault.run_once(db, api, "creator-1"))["folders"] == 1

    async def test_ta_ista_fotka_v_dvoch_priecinkoch_pribudne_raz(self):
        api = FakeApi(
            [{"name": "A"}, {"name": "B"}], {"A": [item("dup")], "B": [item("dup")]}
        )
        db = FakeDb()
        out = await fvvault.run_once(db, api, "creator-1")
        assert out["media_new"] == 1 and len(db.upserted) == 1

    async def test_bez_creator_uuid_to_skonci_chybou(self):
        """Nepripojený účet nesmie skončiť tichým „0 priečinkov"."""
        with pytest.raises(ValueError):
            await fvvault.run_once(FakeDb(), FakeApi([], {}), "")


# ---------------------------------------------------------------------------
# Fronta
# ---------------------------------------------------------------------------


class QueueDb(FakeDb):
    def __init__(self, requests, settings=None, **kw):
        super().__init__(**kw)
        self._requests = list(requests)
        self._settings = settings if settings is not None else {"creator_uuid": "creator-1"}
        self.started = []
        self.finished = []
        self.pruned = []

    async def settings(self):
        return dict(self._settings)

    async def prune_sync(self, older_than_h=24):
        self.pruned.append(older_than_h)

    async def pending_sync(self):
        return self._requests.pop(0) if self._requests else None

    async def start_sync(self, request_id):
        self.started.append(request_id)

    async def finish_sync(self, request_id, ok, folders=0, media_new=0, media_seen=0, error=""):
        self.finished.append(
            {"id": request_id, "ok": ok, "folders": folders,
             "media_new": media_new, "media_seen": media_seen, "error": error}
        )


class TestFronta:
    async def test_prazdna_fronta_nic_nerobi(self):
        db = QueueDb([])
        assert await fvvault.VaultSync(db, FakeApi([], {})).tick() is False
        assert db.started == [] and db.finished == []

    async def test_poziadavka_sa_vykona_a_uzavrie(self):
        db = QueueDb([{"id": 9}])
        api = FakeApi([{"name": "Posts"}], {"Posts": [item("a")]})
        assert await fvvault.VaultSync(db, api).tick() is True
        assert db.started == [9]
        assert db.finished == [
            {"id": 9, "ok": True, "folders": 1, "media_new": 1, "media_seen": 1, "error": ""}
        ]

    async def test_zlyhanie_riadok_uzavrie_tiez(self):
        """Otvorená požiadavka je zámok — tlačidlo by ostalo mŕtve navždy."""
        db = QueueDb([{"id": 3}], settings={"creator_uuid": ""})
        assert await fvvault.VaultSync(db, FakeApi([], {})).tick() is True
        assert db.started == [3]
        assert db.finished[0]["ok"] is False and db.finished[0]["error"]

    async def test_chyba_z_api_neunikne_do_slucky(self):
        class Vybuchne(FakeApi):
            async def vault_folders(self, creator_uuid):
                raise RuntimeError("401 Unauthorized")

        db = QueueDb([{"id": 4}])
        assert await fvvault.VaultSync(db, Vybuchne([], {})).tick() is True
        assert "401" in db.finished[0]["error"]

    async def test_creator_uuid_ide_z_nastaveni_modelky(self):
        db = QueueDb([{"id": 1}], settings={"creator_uuid": "creator-XYZ"})
        api = FakeApi([], {})
        await fvvault.VaultSync(db, api).tick()
        assert api.asked == ["creator-XYZ"]


class TestUpratovanieFronty:
    """Dobehnuté požiadavky nikto nemazal a tabuľka rástla donekonečna.

    Dashboard z fronty číta jedinú vec — ako dopadol POSLEDNÝ klik. Riadok
    spred týždňa už nikto neuvidí, ale pri modelke, ktorá synchronizuje denne,
    ich za rok pribudnú stovky.
    """

    async def test_prve_kolo_uprace(self):
        db = QueueDb([])
        assert await fvvault.VaultSync(db, FakeApi([], {})).maybe_prune() is True
        assert db.pruned == [fvvault.PRUNE_OLDER_THAN_H]

    async def test_dalsie_kolo_hned_neuprataava(self):
        """Fronta sa pozerá každé 4 s — mazanie pri každom kole by bol dotaz
        navyše pri každom kole každej modelky."""
        db = QueueDb([])
        sync = fvvault.VaultSync(db, FakeApi([], {}))
        await sync.maybe_prune()
        assert await sync.maybe_prune() is False
        assert db.pruned == [fvvault.PRUNE_OLDER_THAN_H]

    async def test_po_uplynuti_intervalu_uprace_znova(self):
        db = QueueDb([])
        sync = fvvault.VaultSync(db, FakeApi([], {}), prune_every_s=0)
        await sync.maybe_prune()
        await sync.maybe_prune()
        assert len(db.pruned) == 2

    async def test_zlyhanie_upratovania_nezhodi_synchronizaciu(self):
        db = QueueDb([{"id": 1}])

        async def boom(older_than_h=24):
            raise RuntimeError("supabase down")

        db.prune_sync = boom
        sync = fvvault.VaultSync(db, FakeApi([{"name": "Posts"}], {"Posts": [item("a")]}))
        assert await sync.maybe_prune() is False
        assert await sync.tick() is True          # fronta beží ďalej

    async def test_zlyhanie_sa_skusi_znova_az_po_intervale(self):
        """Padajúca Supabase nesmie znamenať mazací pokus každé 4 sekundy."""
        db = QueueDb([])

        async def boom(older_than_h=24):
            raise RuntimeError("supabase down")

        db.prune_sync = boom
        sync = fvvault.VaultSync(db, FakeApi([], {}))
        assert await sync.maybe_prune() is False
        assert await sync.maybe_prune() is False   # druhý pokus sa ani nespustí


class TestNajstarsiaCakajuca:
    def test_vyberie_najnizsie_id(self):
        rows = [{"id": 5}, {"id": 2, "finished_at": None}, {"id": 9}]
        assert fvvault.newest_pending(rows)["id"] == 2

    def test_dokoncene_sa_nepocitaju(self):
        rows = [{"id": 1, "finished_at": "2026-08-17T00:00:00Z"}]
        assert fvvault.newest_pending(rows) is None

    def test_prazdny_zoznam(self):
        assert fvvault.newest_pending([]) is None
