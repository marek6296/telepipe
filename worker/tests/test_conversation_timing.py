from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

import conversation_timing as timing

NOW = datetime(2026, 11, 16, 18, tzinfo=timezone.utc).astimezone(ZoneInfo('America/Los_Angeles'))


def row(role, content, stamp=None, **extra):
    return dict(role=role, content=content, occurred_at=stamp, **extra)


def reopened():
    return [
        row('assistant', 'I tried a new recipe', '2026-11-15T23:33:30Z'),
        row('user', 'How did it turn out?', '2026-11-16T02:38:53Z'),
        row('user', 'Hi beautiful', '2026-11-16T17:40:52Z'),
        row('user', 'You there honey', '2026-11-16T17:44:07Z'),
    ]


def test_new_greeting_and_checkin_are_one_current_turn_with_old_question_in_background():
    raw = reopened()
    before = deepcopy(raw)
    turn = timing.analyze(raw, now_local=NOW)
    assert turn.latest_text == 'Hi beautiful\nYou there honey'
    assert turn.has_greeting and turn.starts_new_session
    assert not turn.greeting_only
    assert turn.older_unanswered_count == 1
    assert len(turn.messages) == 4
    assert 'BACKGROUND' in turn.messages[1]['content']
    assert 'CURRENT TURN' in turn.messages[2]['content']
    assert '2026-11-16 09:40 PST' in turn.messages[2]['content']
    assert 'America/Los_Angeles' in turn.prompt
    assert 'new acquaintance' in turn.prompt
    assert raw == before
    assert all(set(m) == {'role', 'content'} for m in turn.messages)


def test_question_after_greeting_in_same_burst_is_not_lost():
    history = reopened()[:-1] + [row('user', 'How did the recipe turn out?', '2026-11-16T17:44:07Z')]
    turn = timing.analyze(history, now_local=NOW)
    assert turn.has_greeting and 'recipe' in turn.latest_text
    assert 'explicitly returns' in turn.prompt
    assert 'recipe' in turn.messages[0]['content']  # old details remain available


def test_midnight_without_long_gap_does_not_reset_the_conversation():
    history = [row('user', 'What recipe?', '2026-11-16T07:59:00Z'), row('user', 'The cake?', '2026-11-16T08:01:00Z')]
    turn = timing.analyze(history, now_local=NOW)
    assert len(turn.incoming) == 2
    assert not turn.starts_new_session


def test_same_day_long_gap_starts_a_new_session_too():
    turn = timing.analyze([row('user', 'morning', '2026-11-16T08:01:00Z'), row('user', 'back now', '2026-11-16T17:01:00Z')], now_local=NOW)
    assert turn.starts_new_session and turn.latest_text == 'back now'


@pytest.mark.parametrize('stamp', [None, '', 'invalid', '2029-11-16T17:00:00Z'])
def test_missing_bad_or_future_source_time_never_uses_import_timestamp(stamp):
    history = [row('user', 'earlier question', stamp, created_at='2026-11-15T02:00:00Z'), row('user', 'Hi', None, created_at='2026-11-16T17:00:00Z')]
    turn = timing.analyze(history, now_local=NOW)
    assert len(turn.incoming) == 2 and not turn.starts_new_session
    assert 'time unknown' in turn.messages[0]['content']


def test_unknown_between_known_messages_does_not_fabricate_a_gap():
    history = reopened()
    history.insert(2, row('assistant', 'another answer', None))
    turn = timing.analyze(history, now_local=NOW)
    assert not turn.starts_new_session
    assert len(turn.incoming) == 2


def test_answered_greeting_is_not_reused():
    history = [row('user', 'Hi'), row('assistant', 'hey'), row('user', 'how is the cake?')]
    turn = timing.analyze(history, now_local=NOW)
    assert not turn.has_greeting
    assert turn.latest_text == 'how is the cake?'


@pytest.mark.parametrize('text', ['Hi beautiful', 'Hey, how are you?', 'good morning!', 'ahoj ako sa mas'])
def test_greetings_detected_before_substantive_content(text):
    assert timing.analyze([row('user', text)], now_local=NOW).has_greeting


@pytest.mark.parametrize('text', ['good question', 'the word hi is funny', 'this is high quality'])
def test_greeting_is_not_a_substring_match(text):
    assert not timing.analyze([row('user', text)], now_local=NOW).has_greeting


def test_regeneration_replaces_old_timing_block_with_fresh_time():
    turn = timing.analyze(reopened(), now_local=NOW)
    old = timing.prompt_with_timing('persona', turn)
    fresh = timing.analyze(reopened(), now_local=NOW.replace(hour=11))
    new = timing.prompt_with_timing(old, fresh)
    assert new.count('[CONVERSATION TIMING]') == 1
    assert '11:00 PST' in new and '10:00 PST' not in new


def test_dst_fold_uses_elapsed_time_and_correct_local_offsets():
    history = [row('user', 'one', '2026-11-01T08:30:00Z'), row('user', 'two', '2026-11-01T09:30:00Z')]
    turn = timing.analyze(history, now_local=NOW)
    assert not turn.starts_new_session
    assert '01:30 PDT' in turn.messages[0]['content']
    assert '01:30 PST' in turn.messages[1]['content']


def test_greeting_only_is_not_confused_with_greeting_plus_checkin():
    assert timing.analyze([row('user', 'hi beautiful')], now_local=NOW).greeting_only
    assert not timing.analyze(reopened(), now_local=NOW).greeting_only


def test_late_import_of_old_answer_cannot_hide_new_inbound():
    history = reopened()[1:] + reopened()[:1]
    turn = timing.analyze(history, now_local=NOW)
    assert turn.latest_text == 'Hi beautiful\nYou there honey'
    assert turn.messages[0]['role'] == 'assistant'


def test_chronology_keeps_unknown_slots_without_guessing_their_time():
    history = [row('user', 'new', '2026-11-16T17:00:00Z'), row('user', 'unknown'), row('assistant', 'old', '2026-11-15T18:00:00Z')]
    ordered = timing.chronological_rows(history, now_local=NOW)
    assert [r['content'] for r in ordered] == ['old', 'unknown', 'new']
