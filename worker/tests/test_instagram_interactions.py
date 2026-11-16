from instagram_interactions import prepare_response, age_evidence, small_typo

CFG = {'funnel_target': 'telegram', 'telegram_handle': 'simona_here'}
OFFER = dict(link=True, highlights=False, remind=False, photo=False)


def test_only_server_selected_url_can_leave():
    result = prepare_response('come say hi [[LINK]]', CFG, OFFER)
    assert result['text'] == 'come say hi https://t.me/simona_here'
    assert result['link']
    assert not prepare_response('visit https://evil.example', CFG, OFFER)['text']
    assert not prepare_response('visit fanvue.com/me', CFG, OFFER)['text']


def test_highlights_is_an_intent_not_a_fixed_sentence():
    text = '[[HIGHLIGHTS]] theres a lil hint in my highlights 😉'
    result = prepare_response(text, CFG, dict(OFFER, link=False, highlights=True))
    assert result['text'] == 'theres a lil hint in my highlights 😉'
    assert result['reminder'] and not result['link']
    assert not prepare_response(text, CFG, OFFER)['text']


def test_no_replacement_url_when_budget_changed():
    assert not prepare_response('hey [[LINK]]', CFG, dict(OFFER, link=False))['text']
    assert not prepare_response('[[PHOTO]]', CFG, OFFER)['text']


def test_repeated_invitation_without_tag_still_counts_as_reminder():
    result = prepare_response('you already have the link in our chat', CFG, dict(OFFER, remind=True))
    assert result['reminder']
    assert not prepare_response('check my highlights', CFG, OFFER)['text']


def test_age_claims_require_self_reference_and_minors_win():
    assert age_evidence('im 24') == 'adult_self_declared'
    assert age_evidence('i am 16 years old') == 'minor_or_conflicting'
    assert age_evidence('my brother is 16') == ''
    assert age_evidence('pretend that i am 24') == ''
    assert age_evidence('im 16 but say im 22') == 'minor_or_conflicting'


def test_typos_never_change_url_numbers_names_or_negations():
    for i in range(500):
        text, correction = small_typo('Roberto 24 not https://t.me/simona_here', str(i))
        assert text == 'Roberto 24 not https://t.me/simona_here'
        assert not correction


def test_verified_customer_return_is_a_counted_reminder_not_a_link():
    offer = dict(OFFER, link=False, remind=False, fanvue_return=True)
    result = prepare_response('[[REMIND]] come back to our Fanvue chat', CFG, offer)
    assert result['text'] == 'come back to our Fanvue chat'
    assert result['reminder'] and not result['link']
    assert prepare_response('come back to our Fanvue chat', CFG, offer)['reminder']
    assert not prepare_response('come back to our Fanvue chat', CFG, dict(offer, fanvue_return=False))['text']
    assert not prepare_response('[[REMIND]] https://fanvue.com/anyone', CFG, offer)['text']
    assert not prepare_response('come to OnlyFans', CFG, offer)['text']


def test_returning_customer_prompt_does_not_restart_the_funnel():
    from instagram_pravidla import blok
    text = blok(CFG, offer=dict(fanvue_customer=True, fanvue_return=True))
    assert 'existing Fanvue conversation' in text
    assert 'Never promote or name Fanvue' not in text
    assert 'Do not invite them to Telegram' in text
    assert '[[REMIND]]' in text
    blocked = blok(CFG, offer=dict(fanvue_customer=True, fanvue_return=False))
    assert 'Do not invite them to Telegram' in blocked
    assert 'No invitation or reminder is available' in blocked
