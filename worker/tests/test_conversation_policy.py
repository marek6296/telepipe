from datetime import datetime, timedelta, timezone

import conversation_policy as policy

NOW = datetime(2026, 11, 16, 22, 0, tzinfo=timezone.utc)


def test_window_uses_platform_time_not_ingestion_and_rejects_future():
    assert policy.in_window(NOW - timedelta(hours=23), NOW)
    assert not policy.in_window(NOW - timedelta(hours=24), NOW)
    assert not policy.in_window(NOW + timedelta(seconds=1), NOW)
    assert not policy.in_window('not a date', NOW)


def test_reply_time_is_stable_and_never_immediate():
    a = policy.choose_due('dm', NOW, 'event-123', active=True)
    assert NOW + timedelta(seconds=45) <= a <= NOW + timedelta(minutes=20)
    assert policy.choose_due('dm', NOW, 'event-123', active=True) == a
    assert policy.choose_due('comment', NOW, 'comment-1') >= NOW + timedelta(minutes=15)


def test_la_day_is_not_utc_day():
    assert policy.day_key(datetime(2026, 11, 17, 3, tzinfo=timezone.utc)) == '2026-11-16'


def candidate(**overrides):
    return dict(id='ig-identity', platform='instagram', external_id='ig-1',
                username='roberto_1978', display_name='Roberto',
                last_invite_at=(NOW - timedelta(minutes=4)).isoformat(),
                invite_target='telegram', **overrides)


def test_recent_invite_and_self_introduction_recognizes_without_verifying():
    current = dict(platform='telegram', username='rob_1978', display_name='Rob',
                   text='hey its me Roberto from instagram')
    hit = policy.identity_candidate(current, [candidate()], NOW)
    assert hit['identity_id'] == 'ig-identity'
    assert hit['status'] == 'recognized'
    assert hit['private_context_allowed'] is False


def test_matching_username_without_invite_only_suggests_confirmation():
    person = candidate()
    person['last_invite_at'] = None
    hit = policy.identity_candidate(dict(platform='telegram', username='roberto_1978'), [person], NOW)
    assert hit['status'] == 'candidate'


def test_ambiguous_matches_and_rejected_identity_are_not_joined():
    a, b = candidate(), candidate()
    b['id'] = 'other'
    current = dict(platform='telegram', username='roberto_1978')
    assert policy.identity_candidate(current, [a, b], NOW) is None
    current['rejected_identity_ids'] = ['ig-identity']
    assert policy.identity_candidate(current, [a], NOW) is None


def test_identity_denial_is_not_generic_disagreement():
    assert policy.identity_denied('no thats not me, im not the guy from instagram')
    assert policy.identity_denied('to nie som ja')
    assert not policy.identity_denied('no i dont like coffee')


def test_story_question_and_emoji_have_different_actions():
    assert policy.input_kind('where is this?', story=True) == 'dm'
    assert policy.input_kind('😍🔥', story=True) == 'reaction'
    assert policy.input_kind('', story=False) == 'unknown'


def test_comment_spam_is_never_selected_and_selection_does_not_reroll():
    assert policy.select_comment('buy followers click my profile', 'id-1') is False
    assert policy.select_comment('lovely picture', 'id-2') == policy.select_comment('lovely picture', 'id-2')


def test_allowed_destination_requires_exact_safe_https_url():
    assert policy.allowed_destination('bio_link', {'bio_link': 'https://linkovne.com/simona'}) == 'https://linkovne.com/simona'
    assert not policy.allowed_destination('bio_link', {'bio_link': 'https://linkovne.com.evil.test/simona'})
    assert not policy.allowed_destination('bio_link', {'bio_link': 'https://user:password@linkovne.com/a'})
    assert not policy.allowed_destination('bio_link', {'bio_link': 'javascript:alert(1)'})
    assert policy.allowed_destination('telegram', {'telegram_handle': 'simapussina'}) == 'https://t.me/simapussina'


def test_opt_out_is_typed_and_does_not_confuse_no_links_with_no_contact():
    assert policy.opt_out('please stop sending links') == 'links'
    assert policy.opt_out('dont message me again') == 'contact'
    assert policy.opt_out('no thanks i already ate') == ''
