"""Stropy odchádzajúcich správ — čo vlastne vyzerá ako rozposielanie."""
import limity


class TestStropNaOslovenie:
    """Strop je na to, komu sa ozve SAMA — nie na odpovede.

    Odpovedať tomu, kto napísal prvý, nie je vzor, ktorý by komukoľvek vadil.
    Podozrivé je opačné poradie.
    """

    def test_kto_uz_dostal_prejde_vzdy(self):
        assert limity.smie_oslovit(5, {5, 1, 2, 3}, max_za_hodinu=3)

    def test_novy_nad_strop_neprejde(self):
        assert not limity.smie_oslovit(9, {1, 2, 3}, max_za_hodinu=3)

    def test_novy_pod_stropom_prejde(self):
        assert limity.smie_oslovit(9, {1, 2}, max_za_hodinu=3)

    def test_nula_vypina_strop(self):
        assert limity.smie_oslovit(9, set(range(100)), max_za_hodinu=0)


class TestVyberKohoOslovit:
    def test_zachova_poradie(self):
        assert limity.koho_oslovit([7, 8, 9], set(), 5, 5) == [7, 8, 9]

    def test_kazdy_novy_zaberie_miesto_dalsiemu(self):
        out = limity.koho_oslovit([1, 2, 3, 4, 5], set(), max_za_hodinu=2, volnych_sprav=5)
        assert out == [1, 2]

    def test_strop_na_spravy_plati_tiez(self):
        out = limity.koho_oslovit([1, 2, 3], set(), max_za_hodinu=99, volnych_sprav=2)
        assert out == [1, 2]

    def test_nulovy_pocet_sprav_pusti_nikoho(self):
        assert limity.koho_oslovit([1, 2], set(), 99, 0) == []


class TestFloodChyby:
    """Skutočné triedy z Telethonu, nie napodobeniny.

    Práve na tomto testy predtým prešli falošne: kód porovnával názvy tried
    ako reťazce, takže by ticho minul podtriedu aj premenovanie.
    """

    def test_floodwait_vrati_cas_od_telegramu(self):
        from telethon.errors import FloodWaitError

        assert limity.flood_pauza_s(FloodWaitError(request=None, capture=42)) == 42

    def test_peerflood_je_dlha_pauza(self):
        from telethon.errors import PeerFloodError

        exc = PeerFloodError(request=None)
        assert limity.flood_pauza_s(exc) == limity.PEER_FLOOD_PAUZA_H * 3600
        assert limity.je_spam_priznak(exc)

    def test_bezna_chyba_nie_je_flood(self):
        assert limity.flood_pauza_s(RuntimeError("sieť spadla")) is None
        assert not limity.je_spam_priznak(RuntimeError("x"))

    def test_pomale_pasmo_sa_bere_tiez(self):
        from telethon.errors import SlowModeWaitError

        assert limity.flood_pauza_s(SlowModeWaitError(request=None, capture=30)) == 30

    def test_nula_sekund_stale_znamena_chvilu_pockat(self):
        from telethon.errors import FloodWaitError

        assert limity.flood_pauza_s(FloodWaitError(request=None, capture=0)) >= 1


class TestMiestaPreRozhovory:
    """Skutočný človek nevedie dvadsať rozhovorov naraz.

    Vedie pár, tie dopíše, a keď utíchnu, pustí sa do ďalších.
    """

    def test_kto_uz_pise_pokracuje_vzdy(self):
        """Rozhovor sa nesmie preseknúť len preto, že napísal niekto ďalší."""
        assert limity.ma_miesto(3, {1, 2, 3, 4, 5}, max_naraz=5)

    def test_novy_cez_plne_miesta_pocka(self):
        assert not limity.ma_miesto(9, {1, 2, 3, 4, 5}, max_naraz=5)

    def test_ked_sa_miesto_uvolni_pusti_dalsieho(self):
        """Toto je celé jadro: štvrtý utíchol, piaty ide na rad."""
        assert limity.ma_miesto(9, {1, 2, 3}, max_naraz=5)

    def test_nula_znamena_pise_vsetkym(self):
        assert limity.ma_miesto(99, set(range(50)), max_naraz=0)

    def test_jeden_dvaja_ludia_nie_su_nikdy_brzdeni(self):
        for aktivni in (set(), {1}, {1, 2}):
            assert limity.ma_miesto(7, aktivni, max_naraz=5)


class TestKtoIdeNaRad:
    def test_pusti_len_tolko_kolko_je_miest(self):
        out = limity.kto_ide_na_rad([10, 11, 12, 13], {1, 2, 3}, max_naraz=5, volnych_sprav=99)
        assert out == [10, 11]

    def test_kto_caka_najdlhsie_ide_prvy(self):
        """Fronta prichádza zoradená — poradie sa musí zachovať."""
        out = limity.kto_ide_na_rad([77, 88, 99], set(), max_naraz=1, volnych_sprav=99)
        assert out == [77]

    def test_rozbehnute_rozhovory_miesta_neberu_znova(self):
        out = limity.kto_ide_na_rad([1, 2, 9], {1, 2}, max_naraz=2, volnych_sprav=99)
        assert out == [1, 2], "obaja pokračujú, deviaty počká"

    def test_strop_na_spravy_plati_aj_tu(self):
        out = limity.kto_ide_na_rad([10, 11, 12], set(), max_naraz=9, volnych_sprav=2)
        assert out == [10, 11]

    def test_vypnute_miesta_pustia_vsetkych(self):
        out = limity.kto_ide_na_rad([1, 2, 3], set(), max_naraz=0, volnych_sprav=99)
        assert out == [1, 2, 3]
