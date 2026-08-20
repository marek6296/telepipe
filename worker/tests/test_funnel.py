from datetime import datetime, timedelta, timezone

import funnel

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def user(**kw):
    base = {
        "tg_id": 1,
        "funnel_stage": funnel.COLD,
        "msg_count": 1,
        "link_push_count": 0,
        "link_sent_at": None,
        "paid": False,
    }
    base.update(kw)
    return base


class TestDetectInterest:
    def test_detects_content_request(self):
        assert funnel.detect_interest("posli mi nejake fotky")

    def test_detects_price_question(self):
        assert funnel.detect_interest("kolko to stoji?")

    def test_ignores_small_talk(self):
        assert not funnel.detect_interest("ako sa mas dnes")


class TestNextStage:
    def test_cold_stays_cold_on_small_talk(self):
        assert funnel.next_stage(user(msg_count=1), "ahoj") == funnel.COLD

    def test_cold_warms_on_interest(self):
        assert funnel.next_stage(user(msg_count=1), "mas nejake fotky?") == funnel.WARM

    def test_cold_warms_after_three_messages(self):
        assert funnel.next_stage(user(msg_count=3), "aha") == funnel.WARM

    def test_link_sent_does_not_regress(self):
        assert funnel.next_stage(user(funnel_stage=funnel.LINK_SENT, msg_count=9), "fotky") == funnel.LINK_SENT

    def test_paid_user_is_converted(self):
        assert funnel.next_stage(user(paid=True, msg_count=2), "ahoj") == funnel.CONVERTED


class TestCanSendLink:
    def test_blocked_while_cold(self):
        assert not funnel.can_send_link(user(msg_count=10), NOW, 6, 48, 3)

    def test_blocked_before_min_messages(self):
        u = user(funnel_stage=funnel.WARM, msg_count=5)
        assert not funnel.can_send_link(u, NOW, 6, 48, 3)

    def test_allowed_when_warm_and_enough_messages(self):
        u = user(funnel_stage=funnel.WARM, msg_count=6)
        assert funnel.can_send_link(u, NOW, 6, 48, 3)

    def test_blocked_inside_cooldown(self):
        u = user(
            funnel_stage=funnel.WARM,
            msg_count=20,
            link_push_count=1,
            link_sent_at=(NOW - timedelta(hours=5)).isoformat(),
        )
        assert not funnel.can_send_link(u, NOW, 6, 48, 3)

    def test_allowed_after_cooldown(self):
        u = user(
            funnel_stage=funnel.WARM,
            msg_count=20,
            link_push_count=1,
            link_sent_at=(NOW - timedelta(hours=50)).isoformat(),
        )
        assert funnel.can_send_link(u, NOW, 6, 48, 3)

    def test_blocked_after_max_pushes(self):
        u = user(
            funnel_stage=funnel.WARM,
            msg_count=40,
            link_push_count=3,
            link_sent_at=(NOW - timedelta(days=30)).isoformat(),
        )
        assert not funnel.can_send_link(u, NOW, 6, 48, 3)

    def test_blocked_for_paying_user(self):
        u = user(funnel_stage=funnel.WARM, msg_count=20, paid=True)
        assert not funnel.can_send_link(u, NOW, 6, 48, 3)

    def test_handles_zulu_timestamp(self):
        u = user(
            funnel_stage=funnel.WARM,
            msg_count=20,
            link_push_count=1,
            link_sent_at="2026-08-11T10:00:00Z",
        )
        assert not funnel.can_send_link(u, NOW, 6, 48, 3)


class TestPaidClaim:
    def test_detects_claim(self):
        assert funnel.detect_paid_claim("uz som zaplatil, kde to najdem")

    def test_ignores_other_text(self):
        assert not funnel.detect_paid_claim("co robis vecer")


class TestPripomenutieOdkazu:
    """Odkaz nesmie byť v každej správe — z chatu je potom reklama."""

    @staticmethod
    def _jej(*texty):
        return [{"role": "assistant", "content": t} for t in texty]

    def test_nedavnu_zmienku_pozna(self):
        assert funnel.recently_reminded(self._jej("its all on my page hun"))

    def test_pozna_aj_ine_formulacie(self):
        assert funnel.recently_reminded(self._jej("u already got the link higher up"))
        assert funnel.recently_reminded(self._jej("check fanvue babe"))

    def test_po_piatich_spravach_smie_znova(self):
        rows = self._jej("on my page", "haha", "yeah", "mmm", "so true", "totally")
        assert not funnel.recently_reminded(rows)

    def test_jeho_spravy_sa_nepocitaju(self):
        rows = [{"role": "user", "content": "whats your page?"}] * 8
        assert not funnel.recently_reminded(rows)

    def test_prazdna_historia(self):
        assert not funnel.recently_reminded([])


class TestKedySamaVedie:
    """Kto sa nikdy nespýta, toho treba naviesť — inak je to kamarátstvo zadarmo."""

    TERAZ = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def _clovek(cls, hodin=30, **kw):
        row = {"msg_count": 30, "link_push_count": 0, "paid": False, "funnel_stage": "warm",
               "created_at": (cls.TERAZ - timedelta(hours=hodin)).isoformat()}
        row.update(kw)
        return row

    def test_na_druhy_den_ano(self):
        assert funnel.should_lead(self._clovek(), self.TERAZ)

    def test_prvy_den_nikdy(self):
        """Kto dostane pozvánku v deň zoznámenia, vie, že bol cieľ."""
        assert not funnel.should_lead(self._clovek(hodin=6), self.TERAZ)

    def test_kratka_konverzacia_nie(self):
        assert not funnel.should_lead(self._clovek(msg_count=8), self.TERAZ)

    def test_kto_uz_odkaz_dostal_nie(self):
        assert not funnel.should_lead(self._clovek(link_push_count=1), self.TERAZ)

    def test_kto_zaplatil_nie(self):
        assert not funnel.should_lead(self._clovek(paid=True), self.TERAZ)
        assert not funnel.should_lead(self._clovek(funnel_stage="converted"), self.TERAZ)


class TestHovorASretnutie:
    """Odmietnuť natvrdo je strata — má to nechať otvorené a napínavé."""

    def test_pozna_ziadost(self):
        for text in ["lets call", "can we video call?", "facetime me babe",
                     "wanna meet up sometime", "can i see you in person",
                     "do u wanna go on cam", "we should meet up"]:
            assert funnel.wants_call(text), text

    def test_bezny_text_nie(self):
        for text in ["hey how was ur day", "call it a night", "i called my mom today"]:
            assert not funnel.wants_call(text), text


class TestMenoZHolejOdpovede:
    """Holé „Gerard" je najčastejšia odpoveď na otázku o mene.

    Kým prepadávalo, `partner_name` ostalo prázdne — a `humanize.enforce_name`
    bez mena nemá čo vynucovať, takže si ho model vytiahol z histórie a používal
    ho v každej piatej správe. Na jednej modelke bolo prázdnych 5 z 5
    konverzácií a meno používala 4× častejšie, než návrh dovoľuje.
    """

    def test_hole_meno_po_otazke(self):
        for text, ocakavane in [
            ("Gerard", "Gerard"),
            ("Marek and you? :)", "Marek"),
            ("Rafael", "Rafael"),
            ("Ruto", "Ruto"),
        ]:
            assert funnel.extract_name(text, just_asked=True) == ocakavane, text

    def test_bez_otazky_sa_meno_nehada(self):
        """Mimo odpovede na otázku by z každého prvého slova bolo meno."""
        for text in ("Gerard", "Marek and you? :)", "Rafael"):
            assert funnel.extract_name(text) == ""

    def test_bezne_zaciatky_nie_su_mena(self):
        """Presne tieto sa v ostrej prevádzke uložili ako meno: „Actually", „Im"."""
        for text in ("im good", "Actually", "sorry", "yeah", "Honestly nothing", "lol"):
            assert funnel.extract_name(text, just_asked=True) == "", text

    def test_dlha_odpoved_nie_je_predstavenie(self):
        assert funnel.extract_name("i had a really long day at work today", just_asked=True) == ""

    def test_cela_veta_funguje_aj_bez_otazky(self):
        assert funnel.extract_name("my name is Gerard") == "Gerard"
        assert funnel.extract_name("Im Marek") == "Marek"
