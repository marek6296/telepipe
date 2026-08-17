import memory
from persona import build_system_prompt

PERSONA = {
    "name": "Lucia",
    "age": 23,
    "city": "Bratislava",
    "backstory": "Študuje dizajn, rada beha.",
    "tone": "hravá, mierne drzá",
    "msg_style": "krátke správy, malé písmená",
    "boundaries": "nikdy nesľubuj osobné stretnutie",
    "funnel_rules": "najprv sa bav, potom spomeň exkluzívny obsah",
    "cta_link": "https://fanvue.com/lucia",
}


class TestChatHistory:
    def test_converts_rows(self):
        rows = [
            {"role": "user", "content": "ahoj"},
            {"role": "assistant", "content": "cau"},
        ]
        assert memory.to_chat_history(rows) == [
            {"role": "user", "content": "ahoj"},
            {"role": "assistant", "content": "cau"},
        ]

    def test_merges_consecutive_same_role(self):
        rows = [
            {"role": "user", "content": "ahoj"},
            {"role": "user", "content": "si tam?"},
            {"role": "assistant", "content": "som"},
        ]
        assert memory.to_chat_history(rows) == [
            {"role": "user", "content": "ahoj\nsi tam?"},
            {"role": "assistant", "content": "som"},
        ]

    def test_drops_empty_and_unknown_roles(self):
        rows = [
            {"role": "system", "content": "x"},
            {"role": "user", "content": "  "},
            {"role": "user", "content": "ok"},
        ]
        assert memory.to_chat_history(rows) == [{"role": "user", "content": "ok"}]


class TestNeedsSummary:
    def test_true_when_enough_new_messages(self):
        assert memory.needs_summary({"msg_count": 15, "summary_at_msg": 0}, 15)

    def test_false_when_not_yet(self):
        assert not memory.needs_summary({"msg_count": 14, "summary_at_msg": 0}, 15)

    def test_counts_from_last_summary(self):
        assert not memory.needs_summary({"msg_count": 20, "summary_at_msg": 15}, 15)
        assert memory.needs_summary({"msg_count": 30, "summary_at_msg": 15}, 15)


class TestTranscript:
    def test_labels_speakers(self):
        rows = [
            {"role": "user", "content": "ahoj"},
            {"role": "assistant", "content": "cau"},
        ]
        assert memory.transcript_for_summary(rows, "Lucia") == "On: ahoj\nLucia: cau"


class TestSystemPrompt:
    def test_includes_identity_and_style(self):
        prompt = build_system_prompt(PERSONA, {"funnel_stage": "warm", "msg_count": 4}, False, False)
        assert "Si Lucia." in prompt
        assert "23 rokov" in prompt
        assert "krátke správy" in prompt

    def test_forbids_link_when_not_allowed(self):
        prompt = build_system_prompt(PERSONA, {"funnel_stage": "warm", "msg_count": 4}, False, False)
        assert "ODKAZ JE TERAZ ZAKÁZANÝ" in prompt
        assert "fanvue.com/lucia" not in prompt

    def test_offers_link_when_allowed(self):
        prompt = build_system_prompt(PERSONA, {"funnel_stage": "warm", "msg_count": 8}, True, False)
        assert "ODKAZ JE TERAZ POVOLENÝ" in prompt
        assert "https://fanvue.com/lucia" in prompt

    def test_no_greeting_rule_for_ongoing_chat(self):
        prompt = build_system_prompt(PERSONA, {"funnel_stage": "warm", "msg_count": 5}, False, False)
        assert "POKRAČUJÚCA konverzácia" in prompt

    def test_first_message_has_no_ongoing_rule(self):
        prompt = build_system_prompt(PERSONA, {"funnel_stage": "cold", "msg_count": 1}, False, False)
        assert "POKRAČUJÚCA konverzácia" not in prompt

    def test_includes_summary_when_present(self):
        user = {"funnel_stage": "warm", "msg_count": 20, "summary": "Volá sa Peter, z Košíc."}
        prompt = build_system_prompt(PERSONA, user, False, False)
        assert "Peter" in prompt

    def test_converted_stage_disables_selling(self):
        prompt = build_system_prompt(PERSONA, {"funnel_stage": "converted", "msg_count": 30}, False, False)
        assert "Žiadny predaj" in prompt

    def test_ai_question_adds_honesty_rule(self):
        prompt = build_system_prompt(PERSONA, {"funnel_stage": "warm", "msg_count": 5}, False, True)
        assert "OBVIŇUJE ŤA, ŽE SI BOT" in prompt
        # Obhajovanie je presne to, čím sa bot prezradí — musí byť zakázané.
        assert "nie som bot" in prompt and "TAKTO NIE" in prompt


class TestUkazkyStylu:
    """Ukážka funguje lepšie než opis — model sa štýl učí zo vzorky."""

    def test_vrati_jeho_posledne_spravy(self):
        rows = [
            {"role": "user", "content": "hey"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "wyd rn"},
            {"role": "user", "content": "u there"},
        ]
        assert memory.his_samples(rows, 2) == ["wyd rn", "u there"]

    def test_popis_prijatej_fotky_nie_je_jeho_pisanie(self):
        rows = [
            {"role": "user", "content": "[poslal fotku: muz v aute]"},
            {"role": "user", "content": "like it?"},
        ]
        assert memory.his_samples(rows) == ["like it?"]

    def test_jej_spravy_sa_nepocitaju(self):
        assert memory.his_samples([{"role": "assistant", "content": "hey"}]) == []
