"""Čo control bot hlási a čo nie.

Notifikácia, ktorá príde neželane, je otravná; notifikácia, ktorá nepríde, je
horšia — klient sa nedozvie, že mu niekto zaplatil. Testy strážia obe strany.
"""
import oznamy


def _event(typ):
    return {"event_type": typ}


class TestFanvueUdalosti:
    def test_odber_a_platba_chodia_defaultne(self):
        """Sú to peniaze. Kto si ich nevypol, chce o nich vedieť."""
        assert oznamy.sprava_k_udalosti(_event("creator.subscription.activated"), None)
        assert oznamy.sprava_k_udalosti(_event("creator.payment.succeeded"), None)

    def test_lajky_a_komentare_defaultne_nechodia(self):
        """Lajkov môžu byť desiatky denne — z bota by bol spam."""
        assert oznamy.sprava_k_udalosti(_event("creator.post.liked"), None) is None
        assert oznamy.sprava_k_udalosti(_event("creator.post.commented"), None) is None

    def test_vypnute_sa_neposle(self):
        vypnute = {"notify_fanvue_payment": False}
        assert oznamy.sprava_k_udalosti(_event("creator.payment.succeeded"), vypnute) is None

    def test_zapnute_sa_posle(self):
        zapnute = {"notify_fanvue_like": True}
        assert oznamy.sprava_k_udalosti(_event("creator.post.liked"), zapnute)

    def test_spravy_nie_su_oznamy(self):
        """Na správy odpisuje agent — hlásiť ich by znamenalo dvojitú prácu."""
        for typ in ("creator.message.received", "creator.message.sent", "creator.message.read"):
            assert oznamy.sprava_k_udalosti(_event(typ), {"notify_fanvue_like": True}) is None

    def test_neznamy_typ_sa_nehlasi_ale_nespadne(self):
        assert oznamy.sprava_k_udalosti(_event("creator.uplne.nove"), None) is None

    def test_follow_ma_viac_tvarov(self):
        """Nevieme, ktorý tvar Fanvue posiela (ak vôbec) — hádať jeden by
        znamenalo, že notifikácia ticho nikdy nepríde."""
        zapnute = {"notify_fanvue_follow": True}
        for typ in ("creator.follow.created", "creator.follower.added", "follow.created"):
            assert oznamy.sprava_k_udalosti(_event(typ), zapnute), typ

    def test_meno_a_suma_su_v_texte(self):
        text = oznamy.sprava_k_udalosti(
            _event("creator.payment.succeeded"), None, meno_fana="Jane (@jane)", suma="$24.99"
        )
        assert "Jane (@jane)" in text and "$24.99" in text

    def test_chybajuci_riadok_znamena_defaulty_nie_ticho(self):
        """Modelka spred migrácie nemá riadok. Nehlásiť jej nič by bolo horšie."""
        assert oznamy.sprava_k_udalosti(_event("creator.payment.succeeded"), {})


class TestKredit:
    def test_defaultne_chodi(self):
        text = oznamy.sprava_o_kredite(500, None)
        assert text and "500" in text

    def test_da_sa_vypnut(self):
        assert oznamy.sprava_o_kredite(500, {"notify_credits_low": False}) is None

    def test_povie_aj_co_sa_stane(self):
        """Samotné číslo je bez následku — musí byť jasné, že prestane odpisovať."""
        text = oznamy.sprava_o_kredite(100, None)
        assert "stops replying" in text


class TestFormatovanie:
    """Control bot ide cez Telethon = MARKDOWN. Shop bot cez Bot API = HTML.

    Zámena je vidieť okamžite: v chate sa zobrazia holé značky namiesto
    tučného textu. Stalo sa to raz, preto tento test.
    """

    def test_ziadne_html_znacky(self):
        texty = [
            oznamy.sprava_k_udalosti(_event("creator.payment.succeeded"), None, meno_fana="Jane"),
            oznamy.sprava_o_kredite(500, None),
        ]
        for text in texty:
            assert text
            assert "<b>" not in text and "</b>" not in text, text
            assert "<" not in text, text

    def test_pouziva_markdown(self):
        text = oznamy.sprava_o_kredite(500, None)
        assert "*" in text
