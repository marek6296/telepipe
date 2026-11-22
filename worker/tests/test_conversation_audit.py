from unittest.mock import AsyncMock
import pytest
import ludskost
import persona
import zadanie
from conversation_hub import ConversationHub
from test_conversation_hub import Store, identity


def test_shared_persona_does_not_tell_model_to_drop_other_questions():
    prompt = persona.build_system_prompt({'name':'Simona'}, {'msg_count':10},
        allow_link=False, asked_if_ai=False, his_question='where do you live?')
    assert 'Neodpovedaj na všetko, čo napísal' not in prompt
    assert 'Ostatné jeho správy môžeš odbiť' not in prompt
    assert 'všetky podstatné otázky' in prompt
    assert 'KEĎ SI SA POMÝLILA' in prompt


def test_say_this_keeps_owner_intent_beyond_old_500_character_cutoff():
    brief = ('this is background ' * 40) + 'Please tell him I am from Cali and ask where he lives'
    prompt = zadanie.do_promptu(brief)
    assert 'Please tell him I am from Cali and ask where he lives' in prompt
    assert 'Zachovaj celý význam' in prompt


@pytest.mark.parametrize('source,expected', [('2026-11-16T09:00:00+00:00',False),('2026-11-16T11:00:00+00:00',True),(None,False)])
async def test_fanvue_optin_uses_source_time_even_if_imported_after_stop(source, expected):
    t = Store()
    t.rows['/conversation_identities'] = [identity('a','fanvue','fan')]
    t.rows['/conversation_people'] = [dict(model_id='m',id='p',no_initiate=True,stopped_at='2026-11-16T10:00:00+00:00')]
    t.rows['/fv_messages'] = [dict(model_id='m',fan_uuid='fan',role='user',content='how are you?',
        created_at='2026-11-17T11:00:00+00:00',occurred_at=source)]
    assert await ConversationHub(t,'m').can_reply('fanvue','fan') is expected
