"""Text-only owner previews independent of the Semi approval queue.

Provider refreshes only reconcile history. The command's source/identity snapshot
is immutable: the caller must fence the result against it after generation.
Nothing here approves, sends, marks read, or changes the owner's reply mode.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import behavior as bhv
import conversation_timing
import den
import facts
import funnel
import humanize
import judge
import memory
import prehlad
import recall
import topics
import zadanie
from persona import build_system_prompt


def _empty():
    return {'suggestions': [], 'hint': ''}


def _plain(values):
    """No media/interaction intents may become an exact-text owner send.

Unknown/malformed double-bracket directives reject the entire candidate rather
than silently converting an unfulfilled media action into a caption. Performance
tags have an established transcript renderer shared with Fanvue voice previews.
"""
    from fvvoice import spoken_only
    result = []
    for value in values or []:
        if not isinstance(value, str) or '[[' in value or ']]' in value:
            continue
        text = spoken_only(value).strip()
        if text and text.upper() != 'SKIP' and text not in result:
            result.append(text)
    return result


async def generate(sender, command):
    """Return textual suggestions; saving and stale-result rejection are caller-owned."""
    channel = command.get('channel')
    external = str(command.get('external_id') or '')
    if not external:
        return _empty()
    seed, brief = str(command.get('id') or ''), str(command.get('brief') or '')
    if channel == 'telegram':
        if command.get('account_scope') != getattr(sender._cfg, 'tg_account_scope', 'primary'):
            return _empty()
        return await _telegram(sender, external, seed, brief)
    if channel == 'fanvue':
        return await _fanvue(sender, command, external, seed, brief)
    if channel == 'instagram':
        import instagram_api as api
        try:
            return await _instagram(sender, command, external, seed, brief)
        except api.InstagramError as exc:
            await sender._delivery.provider_error(exc, during_read=True)
            if exc.kod != 4:
                raise
            return await _instagram_synced(sender, command, external, seed, brief)
    return _empty()


async def _fanvue(sender, command, external, seed, brief):
    from fanvue_agent import local_now, UHLY_ZADANIE, uhly_pre
    db = sender._db
    cfg = await db.settings()
    scope = 'fanvue:' + str(cfg.get('creator_uuid') or '')
    if not cfg.get('connected') or not cfg.get('creator_uuid') or command.get('account_scope') != scope:
        return _empty()
    result = await sender.regenerate(external, seed=seed, brief=brief)
    current = await db.settings()
    if not current.get('connected') or current.get('creator_uuid') != cfg['creator_uuid']:
        return _empty()
    row = await db.fan(external)
    if not row:
        return _empty()
    if not (result or {}).get('suggestions'):
        # regenerate deliberately stays quiet after her latest native reply.
        # An explicit owner preview can still prepare a follow-up. Its preceding
        # sync_only reconciliation raises on read/import failure; False merely
        # means no unanswered fan turn. Reuse the very same situation builder.
        history = await sender._history_rows(external)
        turn = conversation_timing.analyze(history, now_local=local_now(await db.behavior()))
        fan = {'uuid': external, 'handle': str(row.get('handle') or ''),
               'display_name': str(row.get('display_name') or ''),
               'avatar_url': str(row.get('avatar_url') or ''), 'text': turn.latest_text}
        situation = await sender._situacia(fan, row, current)
        prompt = conversation_timing.prompt_with_timing(situation.prompt, turn) + zadanie.do_promptu(brief)
        suggestions = await sender._llm.suggest(prompt, turn.messages,
                                                angles=UHLY_ZADANIE if brief else uhly_pre(row, current), seed=seed)
        result = {'suggestions': suggestions}
    await sender._reconcile({'uuid': external, 'text': ''}, row,
                            mark_read=False, sync_only=True, process_media=False)
    return {'suggestions': _plain((result or {}).get('suggestions')), 'hint': ''}


async def _telegram(sender, external, seed, brief):
    from userbot import UserBot, UHLY_SEMI, UHLY_ZADANIE
    try:
        tg_id = int(external)
    except ValueError:
        return _empty()
    await sender._sync_native_outgoing(tg_id)
    db = sender._db
    user = await db.get_user(tg_id)
    if not user:
        return _empty()
    persona = await db.get_persona()
    behavior = await sender._behavior()
    rows = await db.recent_messages(tg_id, sender._cfg.context_messages)
    now = datetime.now(ZoneInfo(behavior.active_tz))
    turn = conversation_timing.analyze(rows, now_local=now)
    incoming = turn.latest_text
    fact_rows = await db.facts_for(tg_id)
    episodes = await db.episodes_for(tg_id)
    loops = await db.open_loops(tg_id)
    claims = await db.self_claims(tg_id)
    terms = recall.search_terms(incoming)
    hits = await db.search_archive(tg_id, terms) if terms else []
    recent = {(r.get('content') or '')[:60] for r in rows}
    hits = [h for h in hits if (h.get('content') or '')[:60] not in recent]
    schedule = await sender._rozvrh()
    hub = getattr(db, 'hub', None)
    mood = ''
    if hub:
        block, mood = await hub.day(now, schedule)
    else:
        block = den.block_at(now, sender._cfg.supabase_schema, schedule)
    known = facts.known_keys(fact_rows)
    if user.get('partner_name') and 'name' not in known:
        known.append('name')
    asked = user.get('asked_topics') or {}
    sent_at = conversation_timing.message_time({'occurred_at': user.get('last_reply_at')})
    gap = bhv.gap_hours(sent_at, datetime.now(timezone.utc))
    her_recent = [r.get('content') or '' for r in rows if r.get('role') == 'assistant'][-8:]
    # Text-only preview: do not select media, create short links, or promise an
    # asset whose delivery is absent from this exact-text approval flow.
    system = build_system_prompt(
        persona, user, allow_link=False,
        asked_if_ai=humanize.looks_like_ai_question(incoming),
        ai_pressure=humanize.ai_question_count(rows), behavior=behavior,
        gap=gap, last_incoming=incoming, now_local=now,
        fact_sheet=facts.sheet(fact_rows), claims=judge.claims_block(claims),
        episodes=recall.episodes_block(episodes), loops=recall.loops_block(loops),
        archive=recall.archive_block(hits, persona.get('name') or 'Ona'),
        fresh_topics=topics.suggest(asked, now, bhv.part_of_day(now), known_facts=known, seed=str(tg_id)),
        avoid_topics=topics.recently_asked(asked),
        recent_emoji=humanize.recent_emoji(rows),
        situation=den.describe(block), busy=den.busy(block),
        no_photos=True, can_speak=False,
        foreign=humanize.looks_foreign(incoming), bare_greeting=turn.greeting_only,
        his_question=humanize.last_question(incoming),
        filler=humanize.is_filler(incoming), hostile=humanize.is_hostile(incoming),
        misheard=humanize.asks_what_she_said(incoming),
        wants_call=funnel.wants_call(incoming),
        session_h=memory.session_hours(rows), his_samples=memory.his_samples(rows),
        her_recent=her_recent,
    )
    if hub:
        system += await hub.context('telegram', str(tg_id))
        system += hub.mood_prompt(mood)
    system = conversation_timing.prompt_with_timing(system, turn)
    system += prehlad.pokyn_pre_model(rows) + zadanie.do_promptu(brief)
    raw = await sender._llm.suggest(system, turn.messages,
                                    angles=UHLY_ZADANIE if brief else UHLY_SEMI, seed=seed)
    clean = [UserBot._uprav_odpoved(text, behavior, gap, False, her_recent,
                                  he_greeted=turn.has_greeting) for text in _plain(raw)]
    await sender._sync_native_outgoing(tg_id)
    return {'suggestions': _plain(clean), 'hint': ''}


async def _instagram(sender, command, external, seed, brief):
    import instagram_api as api
    from instagram_interactions import prepare_response
    db = sender._db
    cfg = await db.settings()

    def same_account(current):
        return (current.get('connected') and current.get('access_token')
                and current.get('ig_user_id') == command.get('account_scope'))

    if not same_account(cfg):
        return _empty()
    circuit = conversation_timing.message_time({'occurred_at': cfg.get('circuit_until')})
    if circuit and circuit > datetime.now(timezone.utc):
        return (await _instagram_synced(sender, command, external, seed, brief)
                if cfg.get('circuit_reason') == 'meta_4' else _empty())
    previous = await db.actions(igsid='eq.' + external, order='created_at.desc', limit='1')
    # A stored target is a hint only. Its current remote participant is checked
    # before importing any messages into this contact's history.
    target = next((a.get('target_id') for a in previous
                   if (a.get('payload') or {}).get('account_id') == cfg['ig_user_id']), None)
    raw = None
    if target:
        raw = await asyncio.to_thread(api.conversation, cfg['access_token'], target)
    else:
        cursor, visited = '', set()
        deadline = asyncio.get_running_loop().time() + 60
        while asyncio.get_running_loop().time() < deadline:
            page = await asyncio.to_thread(api.conversation_page, cfg['access_token'], cfg['ig_user_id'], cursor)
            raw = next((r for r in page['data'] if api.rozober(r, cfg['ig_user_id'])['igsid'] == external), None)
            cursor = page['after']
            if raw or not cursor or cursor in visited:
                break
            visited.add(cursor)
    if not raw:
        return _empty()

    async def refresh(snapshot):
        if not same_account(await db.settings()):
            return False
        chat = api.rozober(snapshot, cfg['ig_user_id'])
        if chat['igsid'] != external or not chat['spravy']:
            return False
        # bootstrap only suppresses enqueue; it does not modify channel mode.
        await sender._delivery.ingest(snapshot, cfg, bootstrap=True, process_media=False)
        return True

    if not await refresh(raw):
        return _empty()
    user = await db.user(external)
    if not user:
        return _empty()
    suggestions, _ = await sender._navrhy(user, external, cfg, seed=seed, brief=brief)
    latest = await asyncio.to_thread(api.conversation, cfg['access_token'], raw['id'])
    if not await refresh(latest):
        return _empty()
    offer = await sender._delivery.offer_state(cfg, await db.user(external) or user)
    rendered = [prepare_response(s, cfg, offer) for s in suggestions if isinstance(s, str)]
    return {'suggestions': _plain([r['text'] for r in rendered if r['kind'] == 'dm']), 'hint': ''}


async def instagram_preview(sender, command):
    """Owner text preparation uses the inbox snapshot, never delivery state.

    The dispatcher validates pending ownership/suggestions before this call and
    SQL fences source/identity again when storing it. Native history continues
    to sync independently. No Meta call, seen, takeover or mode mutation.
    """
    return await _instagram_synced(sender, command, str(command.get('external_id') or ''),
                                   str(command.get('id') or ''), str(command.get('brief') or ''))


async def _instagram_synced(sender, command, external, seed, brief):
    """Private owner previews, never delivery permission."""
    from instagram_interactions import prepare_response
    db = sender._db
    async def current():
        cfg = await db.settings()
        return cfg if (cfg.get('ig_user_id') and cfg.get('ig_user_id') == command.get('account_scope')) else None
    cfg = await current()
    source = await db.latest_message_id(external)
    if not cfg or not source or str(source) != str(command.get('expected_source_id')):
        return _empty()
    user = await db.user(external)
    if not user:
        return _empty()
    suggestions, _ = await sender._navrhy(user, external, cfg, seed=seed, brief=brief)
    if not await current() or await db.latest_message_id(external) != source:
        return _empty()
    offer = await sender._delivery.offer_state(cfg, await db.user(external) or user)
    rendered = [prepare_response(s, cfg, offer) for s in suggestions if isinstance(s, str)]
    return {'suggestions': _plain([r['text'] for r in rendered if r['kind'] == 'dm']), 'hint': ''}
