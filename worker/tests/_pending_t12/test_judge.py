"""Sudca — kontrola pred odoslaním, ktorá musí zlyhať otvorene."""
import asyncio

import judge
import pytest

from test_reply_flow import build, user_row

# POZOR: fixture "fast" prepisuje judge.review, takže sa aplikuje LEN na
# triedu, ktorá ide celým tokom. Testy samotného sudcu ju mať nesmú,
# inak by testovali náhradu namiesto skutočného kódu.
NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}


class TestAccept:
    """accept() je jadro bezpečnosti — pri pochybnosti vyhráva pôvodný návrh."""

    def test_ok_verdict_keeps_the_draft(self):
        out = judge.accept("hey you", {"ok": True})
        assert out == {"text": "hey you", "changed": False, "why": ""}

    def test_missing_verdict_keeps_the_draft(self):
        assert judge.accept("hey you", None)["text"] == "hey you"

    def test_applies_a_real_fix(self):
        out = judge.accept("im 25", {"ok": False, "fixed": "im 27", "why": "vek"})
        assert out["text"] == "im 27"
        assert out["changed"] is True

    def test_empty_fix_keeps_the_draft(self):
        out = judge.accept("hey", {"ok": False, "fixed": "   ", "why": "nieco"})
        assert out["text"] == "hey"
        assert out["changed"] is False

    def test_rejects_a_bloated_rewrite(self):
        """Oprava dvojnásobnej dĺžky už nie je oprava."""
        out = judge.accept("hey", {"ok": False, "fixed": "x" * 400, "why": "y"})
        assert out["text"] == "hey"
        assert out["changed"] is False

    def test_allows_a_slightly_longer_fix(self):
        draft = "im from prague"
        out = judge.accept(draft, {"ok": False, "fixed": "im from bratislava actually", "why": "mesto"})
        assert out["changed"] is True


class TestReviewIsSafe:
    def test_llm_failure_sends_the_draft(self):
        class Boom:
            async def structured(self, *_a, **_k):
                raise RuntimeError("model down")

        out = asyncio.run(judge.review(Boom(), "hey you", "hi", "", [], []))
        assert out == {"text": "hey you", "changed": False, "why": ""}

    def test_garbage_verdict_sends_the_draft(self):
        class Junk:
            async def structured(self, *_a, **_k):
                return "toto nie je json"

        out = asyncio.run(judge.review(Junk(), "hey you", "hi", "", [], []))
        assert out["text"] == "hey you"

    def test_empty_draft_short_circuits(self):
        class NeverCalled:
            async def structured(self, *_a, **_k):
                raise AssertionError("nemalo sa volať")

        assert asyncio.run(judge.review(NeverCalled(), "  ", "hi", "", [], []))["text"] == "  "

    def test_fix_is_applied_end_to_end(self):
        class Fixer:
            async def structured(self, *_a, **_k):
                return '{"ok": false, "fixed": "im 27 actually", "why": "vek sedel zle"}'

        out = asyncio.run(judge.review(Fixer(), "im 25", "how old r u", "", [], []))
        assert out["text"] == "im 27 actually"
        assert out["changed"] is True


class TestBrief:
    def test_carries_everything_the_judge_needs(self):
        brief = judge.build_brief(
            "im 25", "how old r u", "- vodič kamiónu", ["má 27 rokov"], ["odkiaľ je"]
        )
        assert "im 25" in brief
        assert "how old r u" in brief
        assert "vodič kamiónu" in brief
        assert "má 27 rokov" in brief
        assert "odkiaľ je" in brief

    def test_skips_empty_sections(self):
        brief = judge.build_brief("hey", "", "", [], [])
        assert "ČO VIE O ŇOM" not in brief
        assert "hey" in brief


class TestSelfClaims:
    def test_parses_a_list(self):
        assert judge.parse_claims('["má sestru v Bratislave", "pracuje v kaviarni"]') == [
            "má sestru v Bratislave",
            "pracuje v kaviarni",
        ]

    def test_broken_json_gives_nothing(self):
        assert judge.parse_claims("nic tu nie je") == []

    def test_drops_too_short(self):
        assert judge.parse_claims('["ok", "má sestru"]') == ["má sestru"]

    def test_block_formats_for_prompt(self):
        assert judge.claims_block([{"claim": "má mačku"}]) == "- má mačku"
        assert judge.claims_block([]) == ""


@pytest.mark.usefixtures("fast")
class TestJudgeInFlow:
    def test_fixed_reply_is_what_gets_sent(self, monkeypatch):
        async def fixer(_llm, draft, *a, **k):
            return {"text": "im 27 babe", "changed": True, "why": "vek"}

        monkeypatch.setattr(judge, "review", fixer)
        bot, db, _, client, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "how old r u"}],
            "im 25 babe",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent[0][1] == "im 27 babe"

    def test_fix_is_logged(self, monkeypatch):
        async def fixer(_llm, draft, *a, **k):
            return {"text": "opravene", "changed": True, "why": "protirečenie"}

        monkeypatch.setattr(judge, "review", fixer)
        bot, db, _, _, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "hey"}],
            "povodne",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert db.judge_logs, "zásah sudcu sa musí zapísať"
        assert db.judge_logs[0][2] == "protirečenie"

    def test_claims_reach_the_prompt(self):
        bot, db, llm, _, _ = build(
            user_row(msg_count=9),
            [{"role": "user", "content": "hey"}],
            "hi",
            behavior=NO_WINDOW,
        )
        db.claim_rows = [{"claim": "má sestru v Bratislave"}]
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "ČO SI MU UŽ O SEBE POVEDALA" in prompt
        assert "sestru v Bratislave" in prompt

    def test_fixed_text_still_goes_through_cleanup(self, monkeypatch):
        """Oprava od sudcu nesmie obísť čistenie typografie."""
        async def fixer(_llm, draft, *a, **k):
            return {"text": "ahoj — to je fajn", "changed": True, "why": "x"}

        monkeypatch.setattr(judge, "review", fixer)
        bot, _, _, client, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "hey"}],
            "povodne",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "—" not in client.sent[0][1], "dlhá pomlčka musí zmiznúť aj po oprave"


class TestOpakovanie:
    """Najčastejšia chyba je, že povie to isté čo pred pár správami."""

    NEDAVNE = [
        "haha u always know what to say honestly",
        "im just chilling at home tonight",
    ]

    def test_najde_zopakovanu_myslienku(self):
        zhody = judge.repeated_phrases(
            "youre so sweet, im just chilling at home tonight too", self.NEDAVNE
        )
        assert zhody, "zopakovanú vetu musí nájsť"
        assert any("chilling" in z for z in zhody)

    def test_nova_veta_neprepadne(self):
        assert judge.repeated_phrases("that sounds rough, how long has it been", self.NEDAVNE) == []

    def test_bezne_slova_nerobia_zhodu(self):
        """„haha ok yeah" sa opakuje prirodzene a opakovaním nie je."""
        assert judge.repeated_phrases("haha yeah ok sure", ["haha yeah ok sure thing"]) == []

    def test_prazdne_vstupy_nepadaju(self):
        assert judge.repeated_phrases("", []) == []
        assert judge.repeated_phrases("hey", []) == []


class TestBriefUpozorniNaOpakovanie:
    def test_zhody_su_v_briefe(self):
        brief = judge.build_brief(
            "im just chilling at home", "wyd", "", [], [],
            ["im just chilling at home tonight"],
        )
        assert "TOTO UŽ RAZ ZAZNELO" in brief
        assert "ČO NEDÁVNO NAPÍSALA" in brief

    def test_bez_historie_ziadne_upozornenie(self):
        brief = judge.build_brief("hey", "hi", "", [], [])
        assert "TOTO UŽ RAZ ZAZNELO" not in brief
