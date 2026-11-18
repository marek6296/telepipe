from unittest.mock import AsyncMock

import pytest

import conversation_timing as timing
from llm import Llm
import zadanie


@pytest.mark.parametrize('method', ['reply', 'suggest'])
async def test_generation_receives_entire_unanswered_burst_as_one_input(method):
    history = [{'role': 'assistant', 'content': 'pretty good and u? what u doing'}] + [
        {'role': 'user', 'content': text} for text in
        ["I'm not doing anything", 'Am good', 'Where in America am I from?']
    ]
    turn = timing.analyze(history)
    model = Llm.__new__(Llm)
    model._so_zalohou = AsyncMock(return_value='one~~~two~~~three')
    await getattr(model, method)(turn.prompt, turn.messages)
    sent = model._so_zalohou.call_args.args[1]
    assert len(sent) == 3  # system, previous answer, full incoming burst
    assert all(text in sent[-1]['content'] for text in ["I'm not doing anything", 'Am good', 'Where in America am I from?'])
    assert 'Each alternative must' in sent[0]['content']


async def test_say_this_preserves_full_brief_in_every_alternative_over_tiny_length():
    model = Llm.__new__(Llm)
    model._so_zalohou = AsyncMock(return_value='one~~~two~~~three')
    await model.suggest(zadanie.do_promptu('Ja som z Cali a ty? :)'), [])
    prompt = model._so_zalohou.call_args.args[1][0]['content']
    assert '5–20 znakov' not in prompt
    assert 'every alternative must preserve' in prompt


def test_batch_keeps_background_separate_and_does_not_mutate_history():
    from copy import deepcopy
    from test_conversation_timing import reopened, NOW
    turn = timing.analyze(reopened(), now_local=NOW)
    original = deepcopy(turn.messages)
    grouped = timing.generation_messages(turn.messages)
    assert len(grouped) == 3
    assert 'BACKGROUND' in grouped[1]['content']
    assert 'CURRENT TURN' not in grouped[1]['content']
    assert 'Hi beautiful' in grouped[2]['content'] and 'You there honey' in grouped[2]['content']
    assert turn.messages == original
    ordinary = [{'role': 'user', 'content': 'one'}, {'role': 'user', 'content': 'two'}]
    assert timing.generation_messages(ordinary) == ordinary
