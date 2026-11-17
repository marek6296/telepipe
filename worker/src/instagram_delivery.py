"""Durable Instagram ingest → queue → fresh context → reserve → single send.

The database owns quotas and leases. A network timeout is an uncertain send,
never permission to retry. Old imports cannot become new inbound messages.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import den
import instagram_api as api
from behavior import Behavior, in_active_window
from conversation_policy import choose_due, in_window, parse_time, select_comment, opt_out, direct_request, reactive_opt_in

log = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def contact_key(key):
    return str(key).split(':', 1)[0]


def unanswered_text(messages):
    for message in reversed(messages):
        if message['role'] != 'user':
            break
        if message.get('kind') == 'dm':
            return message
    return None


class InstagramDelivery:
    def __init__(self, db, agent):
        self.db, self.agent = db, agent
        from social_media import for_db
        self.media = for_db(db, agent._llm)
        self.round = 0

    async def poll(self):
        cfg = await self.db.settings()
        if not cfg.get('connected') or not cfg.get('access_token') or not cfg.get('ig_user_id'):
            return False
        active = cfg.get('enabled') and cfg.get('reply_mode') in ('auto', 'semi')
        if not active:
            await self.db.cancel_actions(reason='channel_off')
            if cfg.get('replies_started_at'):
                await self.db.save({'replies_started_at': None})
                cfg['replies_started_at'] = None
        if not (active or cfg.get('sync_enabled')):
            return False
        if parse_time(cfg.get('circuit_until')) and parse_time(cfg['circuit_until']) > utcnow():
            return True
        self.agent._moje_id = cfg['ig_user_id']
        if not cfg.get('sync_started_at'):
            cfg['sync_started_at'] = utcnow().isoformat()
            await self.db.save({'sync_started_at': cfg['sync_started_at'], 'sync_status': 'importing'})
        if active and not cfg.get('replies_started_at'):
            cfg['replies_started_at'] = utcnow().isoformat()
            await self.db.save({'replies_started_at': cfg['replies_started_at']})
        bootstrap = not cfg.get('sync_completed_at')
        try:
            page = await asyncio.to_thread(api.conversation_page, cfg['access_token'], cfg['ig_user_id'])
            for thread in page['data']:
                await self.ingest(thread, cfg, bootstrap=bootstrap)
            cursor = str(cfg.get('sync_cursor') or '')
            if cursor:
                page = await asyncio.to_thread(api.conversation_page, cfg['access_token'], cfg['ig_user_id'], cursor)
                for thread in page['data']:
                    await self.ingest(thread, cfg, bootstrap=bootstrap)
            patch = {'sync_cursor': page['after'], 'last_poll_at': utcnow().isoformat(), 'poll_error': ''}
            if not page['after']:
                patch.update(sync_completed_at=cfg.get('sync_completed_at') or utcnow().isoformat(), sync_status='ready')
            await self.db.save(patch)
            if active and not bootstrap:
                if self.round % 10 == 0 and cfg.get('reply_comments') and cfg['reply_mode'] == 'auto':
                    await self.comments(cfg)
                await self.process_one(cfg)
            self.round += 1
        except api.InstagramError as exc:
            await self.provider_error(exc)
            return exc.kod != 190
        return True

    async def provider_error(self, exc):
        # Never persist a provider URL or token from exception text.
        patch = {'poll_error': f'Meta error {exc.kod}; delivery paused'}
        if exc.kod == 190:
            patch.update(connected=False, last_error='Instagram access revoked. Reconnect.')
        else:
            patch.update(circuit_until=(utcnow()+timedelta(hours=1)).isoformat(), circuit_reason=f'meta_{exc.kod}')
        await self.db.save(patch)

    async def ingest(self, raw, cfg, bootstrap=False, *, process_media=True):
        chat = api.rozober(raw, cfg['ig_user_id'])
        igsid, messages = chat['igsid'], chat['spravy']
        if not igsid or not messages:
            return
        user = await self.db.ensure_user(igsid, chat['username'])
        known = await self.db.known_mids(igsid)
        processed = await self.db.processed_mids(igsid)
        sent_actions = await self.db.actions(igsid=f'eq.{igsid}', state='in.(sent,sending,uncertain)', order='created_at.desc', limit='100')
        own_mids = {a.get('provider_id') for a in sent_actions if a.get('provider_id')
                    and not (a.get('payload') or {}).get('manual')}
        for message in messages:
            if not message['mid']:
                continue
            if message['mid'] not in known:
                await self.db.add_message(igsid, message['role'], message['content'], message['mid'],
                    occurred_at=(parse_time(message.get('created_time')).isoformat() if parse_time(message.get('created_time')) else None), source='import' if bootstrap else 'meta',
                    metadata={'kind': message.get('kind'), 'has_image': message.get('has_image', False)})
            if message['mid'] in processed:
                continue
            if message['role'] == 'assistant' and message['mid'] not in own_mids:
                # Reconcile only an unambiguous exact text in the bounded send interval.
                stamp = parse_time(message.get('created_time'))
                matches = [a for a in sent_actions if a['state'] in ('sending', 'uncertain')
                    and a['kind'] == 'dm' and a.get('text') == message['content']
                    and parse_time(a.get('reserved_at')) and stamp
                    and parse_time(a['reserved_at'])-timedelta(seconds=5) <= stamp <= parse_time(a['reserved_at'])+timedelta(minutes=2)]
                if len(matches) == 1:
                    a = matches[0]
                    await self.db.rpc('finish', action=a['id'], lease=a['lease_token'], outcome='sent',
                                      provider=message['mid'], reason='reconciled')
                else:
                    # This is a native-app reply, not an instruction to pause all
                    # future replies. Persist history first, then invalidate its
                    # old proposal/commands; mark effects only after both succeed.
                    # Unknown time invalidates conservatively without inventing a
                    # provider timestamp. Manual quota ledger rows are not our echo.
                    occurred = stamp.isoformat() if stamp else None
                    if not await self.db.native_reply(igsid, cfg['ig_user_id'], occurred):
                        return  # The provider account changed while reading.
                    await self.db.cancel_actions(igsid, 'manual_reply', through=occurred)
                    if stamp:
                        await self.db.rpc('record_manual', key=message['mid'], igsid=igsid,
                            occurred=occurred, text=message['content'], photo=bool(message.get('has_image')),
                            account=cfg['ig_user_id'])
            await self.db.mark_message_effects(message['mid'])
        if self.media:
            from social_media import instagram_attachments
            budget = 3
            for message in reversed(messages):
                if message.get('attachments'):
                    if process_media:
                        budget -= int(bool(await self.media.ingest('instagram', igsid, cfg['ig_user_id'], message['mid'],
                            instagram_attachments(message['attachments']))))
                    understood = await self.media.context('instagram', igsid, cfg['ig_user_id'], message['mid'])
                    if understood:
                        message['content'] = understood
                        message['kind'] = 'dm'
                    if budget <= 0:
                        break
        last = messages[-1]
        incoming = next((m for m in reversed(messages) if m['role'] == 'user'), None)
        if incoming:
            patch = {'last_incoming_at': (parse_time(incoming.get('created_time')).isoformat() if parse_time(incoming.get('created_time')) else None), 'last_source_mid': last['mid']}
            if last['role'] == 'user' and last.get('kind') == 'unknown':
                # Consent/age/identity evidence belongs to the usable text, not
                # the opaque placeholder following it. Keep the latest watermark.
                incoming = unanswered_text(messages) or incoming
            from instagram_interactions import age_evidence
            age = age_evidence(incoming['content'])
            if age and user.get('age_state') != 'minor_or_conflicting':
                patch['age_state'] = age
            stop = opt_out(incoming['content'])
            if stop:
                patch['no_links'] = True
                if stop == 'contact':
                    patch['no_initiate'] = True
            await self.db.update_user(igsid, patch)
            user.update(patch)
            if incoming['mid'] != user.get('last_hub_mid'):
                await self.db.hub.observe('instagram', igsid, chat['username'], user.get('name', ''),
                    incoming['content'], scope=cfg['ig_user_id'], source_at=incoming.get('created_time'))
                await self.db.update_user(igsid, {'last_hub_mid': incoming['mid']})
            shared = await self.db.hub.restrictions('instagram', igsid, cfg['ig_user_id'])
            if reactive_opt_in(incoming['content']) or shared.get('stopped_at'):
                if not shared.get('no_initiate'):
                    user['no_initiate'] = False
                    await self.db.update_user(igsid, {'no_initiate': False})
        if last['role'] != 'user':
            await self.db.cancel_actions(igsid, 'outbound_is_latest')
            return
        source = parse_time(last.get('created_time'))
        kind = last.get('kind', 'dm')
        reply_to = last
        if kind == 'unknown':
            # A trailing unsupported attachment must not hide an unanswered DM.
            # Keep freshness tied to the latest event, but NEVER let that unknown
            # event extend the text message's 24-hour window or revive a Skip.
            reply_to = unanswered_text(messages)
            if not reply_to:
                await self.db.cancel_actions(igsid, 'reply_target_missing')
                return
            text_source = parse_time(reply_to.get('created_time'))
            if not source or not in_window(source) or not text_source or not in_window(text_source):
                await self.db.cancel_actions(igsid, 'reply_target_expired')
                return
            terminal = await self.db.actions(igsid=f'eq.{igsid}', state='in.(skipped,sent,sending,uncertain)',
                                             order='created_at.desc', limit='100')
            if any(a.get('source_mid') == reply_to['mid'] or
                   (a.get('payload') or {}).get('reply_to_mid') == reply_to['mid'] for a in terminal):
                await self.db.cancel_actions(igsid, 'reply_target_closed')
                return
            source = min(source, text_source)
            kind = 'dm'
        # A fresh remote snapshot, not enable time, decides whether a DM is unanswered.
        # This also recovers messages received while Off or while the worker was down.
        if (bootstrap or not cfg.get('enabled') or cfg.get('reply_mode') == 'off'
                or not source or not in_window(source)
                or user.get('human_takeover') or not user.get('ai_enabled', True)
                or (user.get('no_initiate') and not direct_request(reply_to['content']))):
            return
        if kind == 'reaction' and not cfg.get('reactions_enabled'):
            return
        due = choose_due(kind, source, f'{self.db.model_id}:{last["mid"]}',
                         active=bool(parse_time(user.get('last_reply_at')) and utcnow()-parse_time(user['last_reply_at']) < timedelta(minutes=15)))
        if cfg.get('reply_mode') == 'semi' and kind == 'dm':
            due = utcnow()  # Owner receives a draft now and chooses when to send.
        # Queue uses provider time and deterministic delay; retries never reroll it.
        queued = await self.db.rpc('enqueue', key=f'{cfg["ig_user_id"]}:{kind}:{last["mid"]}', kind=kind,
            igsid=igsid, target=chat['id'], source_mid=last['mid'], source_at=source.isoformat(),
            due=due.isoformat(), expires=(source+timedelta(hours=24)).isoformat(), payload={
                'account_id': cfg['ig_user_id'], 'requested_reply': direct_request(reply_to['content']),
                **({'reply_to_mid': reply_to['mid']} if reply_to is not last else {})})
        if isinstance(queued, dict) and queued.get('state') == 'approval':
            # A late import can invalidate the proposal while the transport
            # action remains approval for the same unanswered provider MID.
            # SQL atomically excludes live approvals, owner decisions and sends.
            await self.db.requeue_stale_approval(igsid, last['mid'], await self.db.latest_message_id(igsid))

    async def comments(self, cfg):
        posts = await asyncio.to_thread(api.prispevky_s_komentarmi, cfg['access_token'], account_id=cfg['ig_user_id'])
        comments = api.rozober_komentare(posts, cfg['ig_user_id'], cfg.get('username', ''))
        watermark = parse_time(cfg.get('replies_started_at'))
        for comment in comments:
            stamp = parse_time(comment.get('created_time'))
            if not stamp or not watermark or stamp < watermark or not in_window(stamp):
                continue
            selected = select_comment(comment['text'], f'{self.db.model_id}:{comment["comment_id"]}')
            if not selected:
                continue
            await self.db.rpc('enqueue', key=f'{cfg["ig_user_id"]}:comment:{comment["comment_id"]}', kind='comment',
                igsid='', target=comment['comment_id'], source_mid=comment['comment_id'], source_at=stamp.isoformat(),
                due=choose_due('comment', stamp, comment['comment_id']).isoformat(), expires=(stamp+timedelta(hours=24)).isoformat(),
                payload={'account_id': cfg['ig_user_id'], 'comment': comment})

    async def defer(self, action, reason, minutes=15):
        await self.db.change_action(action, {'state': 'pending', 'due_at': (utcnow()+timedelta(minutes=minutes)).isoformat(),
            'lease_token': None, 'lease_until': None, 'reason': reason})

    async def fallback_current(self, action, messages):
        target = (action.get('payload') or {}).get('reply_to_mid')
        if not target:
            return True
        reply_to = unanswered_text(messages)
        if (not reply_to or reply_to['mid'] != target or not in_window(reply_to.get('created_time'))
                or opt_out(reply_to['content']) == 'contact'):
            return False
        terminal = await self.db.actions(igsid=f'eq.{action["igsid"]}', state='in.(skipped,sent,sending,uncertain)',
                                         order='created_at.desc', limit='100')
        return not any(a.get('source_mid') == target or (a.get('payload') or {}).get('reply_to_mid') == target
                       for a in terminal)

    async def refresh_action(self, cfg, action, *, state='leased', source_message_id=None):
        """Import a fresh provider snapshot, then validate this exact reply target."""
        raw = await asyncio.to_thread(api.conversation, cfg['access_token'], action['target_id'])
        await self.ingest(raw, cfg, process_media=False)
        fresh = api.rozober(raw, cfg['ig_user_id'])
        latest = fresh['spravy'][-1] if fresh['spravy'] else {}
        operator = (action.get('payload') or {}).get('origin') == 'operator'
        if (latest.get('mid') != action['source_mid'] or (not operator and latest.get('role') != 'user')
                or not await self.fallback_current(action, fresh['spravy'])):
            await self.db.change_action(action, {'state': 'cancelled', 'reason': 'remote_context_changed'}, state=state)
            return False
        current = await self.db.action(action['id'])
        if not current or current['state'] != state or current.get('source_mid') != action['source_mid']:
            return False
        if source_message_id is not None and await self.db.latest_message_id(action['igsid']) != source_message_id:
            # A late import can change the context without changing the latest
            # provider MID. Generate again instead of sending the old response.
            payload = {k: v for k, v in action.get('payload', {}).items()
                       if k not in ('approved_source_mid', 'approved_intent')}
            await self.db.change_action(action, {
                'state': 'cancelled' if operator else 'pending', 'reason': 'history_changed',
                'text': '', 'payload': payload, 'due_at': utcnow().isoformat(),
                'lease_token': None, 'lease_until': None,
            }, state=state)
            return False
        return True

    async def refresh_regeneration(self, cfg, key):
        parts = str(key).split(':', 1)
        if len(parts) != 2 or not cfg.get('connected') or not cfg.get('access_token'):
            return False
        action = await self.db.action(parts[1])
        if (not action or action['igsid'] != parts[0] or action['state'] != 'approval'
                or (action.get('payload') or {}).get('account_id') != cfg.get('ig_user_id')):
            return False
        return await self.refresh_action(cfg, action, state='approval')

    async def send_readiness(self, cfg, action):
        """Recheck after slow generation/provider reads; Semi only bypasses the clock."""
        current = await self.db.settings()
        if (action.get('payload') or {}).get('origin') == 'operator':
            if not current.get('connected') or current.get('ig_user_id') != cfg.get('ig_user_id'):
                return 'account_changed'
            return '' if in_window(action.get('source_at')) else 'window_expired'
        if (not current.get('enabled') or not current.get('connected')
                or any(current.get(k) != cfg.get(k) for k in ('reply_mode','ig_user_id'))):
            return 'channel_mode_changed'
        if not in_window(action.get('source_at')):
            return 'window_expired'
        if current.get('reply_mode') == 'semi':
            return ''
        behavior = Behavior.from_row(await self.db.behavior())
        local = utcnow().astimezone(ZoneInfo(behavior.active_tz))
        block, _ = await self.db.hub.day(local, den.Rozvrh.from_row(await self.db.schedule()))
        testing = (action['igsid'] and current.get('test_igsid') == action['igsid']
                   and parse_time(current.get('test_until')) and parse_time(current['test_until']) > utcnow())
        return '' if testing or (block and in_active_window(local, behavior.active_start_min, behavior.active_end_min)) else 'sleeping'

    async def process_one(self, cfg, action=None, before_send=None):
        action = action or await self.db.rpc('claim')
        if not action:
            return
        operator = (action.get('payload') or {}).get('origin') == 'operator'
        if operator and before_send is None:
            # Operator work is owned by social_commands. An expired/recovered
            # action must never escape into an automatic retry path.
            await self.db.change_action(action, {'state': 'cancelled', 'reason': 'operator_dispatch_required'})
            return
        # No sending outside the shared local day. The test exception is scoped to
        # one platform ID, expires, and never skips Meta, quota or operator gates.
        local = utcnow()
        if not operator:
            behavior = Behavior.from_row(await self.db.behavior())
            local = local.astimezone(ZoneInfo(behavior.active_tz))
            block, _ = await self.db.hub.day(local, den.Rozvrh.from_row(await self.db.schedule()))
            testing = (action['igsid'] and cfg.get('test_igsid') == action['igsid']
                       and parse_time(cfg.get('test_until')) and parse_time(cfg['test_until']) > utcnow())
            if cfg.get('reply_mode') != 'semi' and not testing and (not block or not in_active_window(local, behavior.active_start_min, behavior.active_end_min)):
                await self.defer(action, 'sleeping')
                return
        link_target = ''
        try:
            if action['kind'] == 'comment':
                # Refresh visible comments; deleted or manually answered comments are cancelled.
                posts = await asyncio.to_thread(api.prispevky_s_komentarmi, cfg['access_token'], account_id=cfg['ig_user_id'])
                fresh = api.rozober_komentare(posts, cfg['ig_user_id'], cfg.get('username', ''))
                comment = next((c for c in fresh if c['comment_id'] == action['target_id']), None)
                if not comment:
                    await self.db.change_action(action, {'state': 'cancelled', 'reason': 'comment_unavailable_or_answered'})
                    return
                text = await self.agent._napis_komentar(comment)
                link = reminder = False
            else:
                raw = await asyncio.to_thread(api.conversation, cfg['access_token'], action['target_id'])
                await self.ingest(raw, cfg, process_media=False)
                user = await self.db.user(action['igsid']) or {}
                current = await self.db.action(action['id'])
                if not current or current['state'] != 'leased':
                    return
                if not await self.fallback_current(action, api.rozober(raw, cfg['ig_user_id'])['spravy']):
                    await self.db.change_action(action, {'state': 'cancelled', 'reason': 'reply_target_changed'})
                    return
                source_message_id = await self.db.latest_message_id(action['igsid'])
                if not operator and cfg['reply_mode'] == 'semi' and not action['payload'].get('approved_source_mid'):
                    if action['kind'] != 'dm':
                        await self.db.change_action(action, {'state': 'skipped', 'reason': 'semi_text_only'})
                        return
                    if not self.agent._control:
                        await self.defer(action, 'approval_unavailable')
                        return
                    proposals, history = await self.agent._navrhy(user, action['igsid'], cfg)
                    if not proposals:
                        await self.defer(action, 'generation_empty')
                        return
                    if reason := await self.send_readiness(cfg, action):
                        await self.defer(action, reason, minutes=0)
                        return
                    if not await self.refresh_action(cfg, action, source_message_id=source_message_id):
                        return
                    # Versioned conversation key: an old card cannot approve a new message.
                    changed = await self.db.change_action(action, {'state': 'approval', 'lease_until': None})
                    if changed:
                        import prehlad
                        ok = await self.agent._control.post_approval(channel='instagram', conv_key=f'{action["igsid"]}:{action["id"]}',
                            display_name=user.get('username') or action['igsid'], incoming_preview=prehlad.blok_rozhovoru(history, now_local=local),
                            suggestions=proposals, hint='Approve at any time. This exact reply still respects the messaging window and delivery limits.',
                            source_message_id=source_message_id)
                        if not ok:
                            # SQL rejected an obsolete publication. Re-read next
                            # poll; there is no provider send to back off or retry.
                            await self.db.change_action(action, {'state': 'pending', 'due_at': utcnow().isoformat()}, state='approval')
                    return
                if action['kind'] == 'reaction':
                    text, link, reminder = '', False, False
                else:
                    if action['kind'] == 'photo':
                        current_offer = await self.offer_state(cfg, user)
                        if not current_offer['photo']:
                            await self.db.change_action(action, {'state': 'blocked', 'reason': 'photo_no_longer_allowed'})
                            return
                    approved_raw = (action['payload'].get('approved_intent')
                        if operator and action['payload'].get('operator_operation') == 'approve' else action.get('text'))
                    raw_text = '[[PHOTO]]' if action['kind'] == 'photo' else approved_raw if action['payload'].get('approved_source_mid') else await self.agent._napis(user, action['igsid'], cfg)
                    from instagram_interactions import prepare_response
                    offer = await self.offer_state(cfg, user)
                    prepared = prepare_response(raw_text or '', cfg, offer)
                    if operator and (prepared['kind'] != 'dm' or not prepared['text'] or prepared['text'] != action['text']):
                        await self.db.change_action(action, {'state': 'blocked', 'reason': 'text_not_allowed'})
                        return
                    if prepared['kind'] == 'photo':
                        photo = await self.db.sfw_photo() if offer['photo'] else None
                        if not photo:
                            await self.defer(action, 'photo_unavailable')
                            return
                        action['kind'] = 'photo'
                        action['payload'] = {**action['payload'], 'photo_id': photo['id'], 'photo_url': photo['url']}
                        if not await self.db.change_action(action, {'kind': 'photo', 'payload': action['payload']}):
                            return
                    text, link, reminder = prepared['text'], prepared['link'], prepared['reminder']
                    link_target = prepared['link_target']
            if not text and action['kind'] not in ('reaction', 'photo'):
                await self.db.change_action(action, {'state': 'skipped', 'reason': 'empty_or_disallowed_response'})
                return
            # Final remote freshness read after generation. DB reservation follows immediately.
            if action['kind'] != 'comment':
                if not await self.refresh_action(cfg, action, source_message_id=source_message_id):
                    return
            correction = {}
            if action['kind'] == 'dm' and cfg.get('typo_enabled') and not action['payload'].get('approved_source_mid') and not link and not reminder:
                from instagram_interactions import small_typo
                text, correction = small_typo(text, action['id'])
            if reason := await self.send_readiness(cfg, action):
                await self.defer(action, reason, minutes=1)
                return
            if operator and not await before_send():
                await self.db.change_action(action, {'state': 'cancelled', 'reason': 'stale_context'})
                return
            reserved = await self.db.rpc('reserve', action=action['id'], lease=action['lease_token'], text=text, link=link, reminder=reminder)
            if not reserved.get('ok'):
                return
            if action['kind'] in ('dm', 'photo'):
                # Read receipts are a separate provider write. Never emit one while
                # polling, generating a proposal, waiting for approval, or blocked.
                try:
                    await asyncio.to_thread(api.mark_seen, cfg['access_token'], cfg['ig_user_id'], action['igsid'])
                except api.InstagramError as exc:
                    # Optional acknowledgement failure must not lose an unsent reply.
                    log.warning('Instagram read receipt unavailable (Meta %s)', exc.kod)
                if reason := await self.send_readiness(cfg, action):
                    await self.db.rpc('release_unsent', action=action['id'], lease=action['lease_token'], reason=reason)
                    return
                if await self.db.latest_message_id(action['igsid']) != source_message_id:
                    await self.db.rpc('release_unsent', action=action['id'], lease=action['lease_token'], reason='history_changed')
                    return
                if operator and not await before_send():
                    await self.db.rpc('release_unsent', action=action['id'], lease=action['lease_token'], reason='stale_context')
                    return
            try:
                if action['kind'] == 'comment':
                    response = await asyncio.to_thread(api.odpovedz_na_komentar, cfg['access_token'], action['target_id'], text)
                elif action['kind'] == 'reaction':
                    response = await asyncio.to_thread(api.react, cfg['access_token'], cfg['ig_user_id'], action['igsid'], action['source_mid'])
                elif action['kind'] == 'photo':
                    response = await asyncio.to_thread(api.send_photo, cfg['access_token'], cfg['ig_user_id'], action['igsid'], action['payload']['photo_url'])
                else:
                    response = await asyncio.to_thread(api.posli_text, cfg['access_token'], action['igsid'], text, account_id=cfg['ig_user_id'])
            except api.InstagramError as exc:
                # Even 5xx can occur after acceptance. Only explicit client rejections release quota.
                outcome = 'failed' if exc.kod in (10, 100, 190, 200, 551) else 'uncertain'
                await self.db.rpc('finish', action=action['id'], lease=action['lease_token'], outcome=outcome, reason=f'meta_{exc.kod}')
                await self.provider_error(exc)
                return
            provider = str(response.get('message_id') or response.get('id') or '')
            # Reactions legitimately acknowledge success without a message id.
            outcome = 'sent' if provider or (action['kind'] == 'reaction' and response.get('success')) else 'uncertain'
            await self.db.rpc('finish', action=action['id'], lease=action['lease_token'], outcome=outcome, provider=provider)
            if outcome == 'sent' and action['kind'] in ('dm', 'photo'):
                await self.db.add_message(action['igsid'], 'assistant', text or '[sent approved photo]', provider)
                if correction:
                    await self.db.update_user(action['igsid'], {'last_typo': correction})
                # A reminder must not overwrite the original invitation destination.
                if link_target:
                    await self.db.hub.record_invite('instagram', action['igsid'],
                        'telegram' if link_target == 'telegram' else 'linkpage', scope=cfg['ig_user_id'])
        except api.InstagramError as exc:
            await self.defer(action, f'refresh_meta_{exc.kod}')
            await self.provider_error(exc)

    async def deliver_operator(self, command, before_send):
        """Prepare a durable action, then run the existing reservation/send path."""
        from social_commands import DeliveryResult
        cfg = await self.db.settings()
        if not cfg.get('connected') or cfg.get('ig_user_id') != command['account_scope']:
            return DeliveryResult.blocked('instagram_disconnected')
        if parse_time(cfg.get('circuit_until')) and parse_time(cfg['circuit_until']) > utcnow():
            return DeliveryResult.blocked('provider_pause')
        raw = None
        previous = await self.db.actions(igsid='eq.' + command['external_id'], order='created_at.desc', limit='1')
        if previous and previous[0].get('target_id'):
            raw = await asyncio.to_thread(api.conversation, cfg['access_token'], previous[0]['target_id'])
        else:
            # Imported Manual contacts have no actions yet; discover their actual
            # thread, paging instead of silently using an unrelated first chat.
            cursor, visited = '', set()
            deadline = asyncio.get_running_loop().time() + 60
            while asyncio.get_running_loop().time() < deadline:
                page = await asyncio.to_thread(api.conversation_page, cfg['access_token'], cfg['ig_user_id'], cursor)
                raw = next((r for r in page['data'] if api.rozober(r, cfg['ig_user_id'])['igsid'] == command['external_id']), None)
                cursor = page['after']
                if raw or not cursor or cursor in visited:
                    break
                visited.add(cursor)
        if not raw:
            return DeliveryResult.blocked('thread_unavailable')
        chat = api.rozober(raw, cfg['ig_user_id'])
        if chat['igsid'] != command['external_id'] or not chat['spravy']:
            return DeliveryResult.blocked('thread_changed')
        await self.ingest(raw, cfg, process_media=False)
        user = await self.db.user(command['external_id']) or {}
        if not in_window(user.get('last_incoming_at')):
            return DeliveryResult.blocked('window_expired', restore_pending=False)
        if command['operation'] == 'approve':
            # Old proposals may contain intents such as [[REMIND]]. The command
            # freezes the exact text/URL shown in the web UI, while the reviewed
            # raw array lets us recover its meaning without inventing a new one.
            from instagram_interactions import prepare_response
            offer = await self.offer_state(cfg, user)
            intent = None
            for candidate in command.get('expected_suggestions') or []:
                if not isinstance(candidate, str):
                    continue
                prepared = prepare_response(candidate, cfg, offer)
                if prepared['kind'] == 'dm' and prepared['text'] and prepared['text'] == command['text']:
                    intent = candidate
                    break
            if intent is None:
                return DeliveryResult.blocked('approved_text_unavailable')
            command = {**command, 'approved_intent': intent}
        if not await before_send():
            return DeliveryResult.blocked('stale_context')
        if command['operation'] == 'send_text' and cfg.get('reply_mode') == 'auto':
            await self.db.update_user(command['external_id'], {'human_takeover': True})
            await self.db.cancel_actions(command['external_id'], 'takeover')
        action = await self.db.prepare_operator_action(command, chat['id'], chat['spravy'][-1]['mid'], user['last_incoming_at'])
        if not action:
            return DeliveryResult.blocked('draft_changed', restore_pending=False)
        try:
            await self.process_one(cfg, action=action, before_send=before_send)
        except Exception:
            # Durable action state determines whether the exception preceded send.
            current = await self.db.action(action['id']) or {}
            if current.get('state') in ('sending', 'uncertain'):
                return DeliveryResult.uncertain()
            if current.get('state') != 'sent':
                raise
        current = await self.db.action(action['id']) or {}
        state = current.get('state')
        if state == 'sent':
            return DeliveryResult('done', result={'provider_message_id': current.get('provider_id') or '',
                                                 'action_id': action['id'], 'delivery_state': 'sent'})
        if state in ('sending', 'uncertain') or not state:
            return DeliveryResult.uncertain()
        if (command.get('pending_id') and state in ('pending', 'ready', 'leased', 'blocked')
                and not current.get('reserved_at')
                and (current.get('payload') or {}).get('command_id') == command['id']):
            payload = {k: v for k, v in (current.get('payload') or {}).items()
                       if k not in ('origin', 'command_id', 'operator_operation', 'approved_intent', 'approved_source_mid')}
            restored = await self.db.change_action(current, {'state': 'approval', 'payload': payload,
                'lease_token': None, 'lease_until': None}, state=state)
            return DeliveryResult.blocked(current.get('reason') or 'delivery_blocked', restore_pending=bool(restored))
        # No provider request happened. Retire any deferred action so no ordinary
        # poll can send it later after this command has reported a safe failure.
        if state in ('pending', 'ready', 'leased'):
            await self.db.change_action(current, {'state': 'cancelled'}, state=state)
        return DeliveryResult.blocked(current.get('reason') or 'delivery_blocked', restore_pending=False)

    async def offer_state(self, cfg, user):
        from instagram_interactions import link_budgets, link_targets
        restrictions = await self.db.hub.restrictions('instagram', user.get('igsid', ''), cfg['ig_user_id'])
        allowed = not (user.get('no_links') or user.get('no_initiate') or restrictions.get('no_links')
                       or restrictions.get('no_initiate') or restrictions.get('age_state') == 'minor_or_conflicting')
        fanvue_customer = bool(await self.db.hub.linked('instagram', user.get('igsid', ''), 'fanvue', cfg['ig_user_id']))
        can_return = allowed
        if fanvue_customer:
            allowed = False
        adult = user.get('age_state') in ('adult_self_declared', 'adult_platform_verified')
        links = await self.db.actions(contains_link='eq.true', reserved_at='not.is.null', order='reserved_at.desc', limit='100')
        budgets = link_budgets(links, cfg, utcnow())
        targets = link_targets(cfg)
        has_link = bool(user.get('link_sent_at'))
        eligible = allowed and adult and not has_link
        telegram_link = bool(eligible and 'telegram' in targets and budgets['telegram'])
        bio_link = bool(eligible and 'bio_link' in targets and budgets['bio_link'])
        reminder_ok = not parse_time(user.get('last_reminder_at')) or utcnow()-parse_time(user['last_reminder_at']) >= timedelta(days=1)
        primary = 'telegram' if cfg.get('funnel_target') == 'both' else cfg.get('funnel_target')
        spent = not budgets.get('bio_link' if 'bio_link' in targets else 'telegram', False)
        return {'fanvue_customer': fanvue_customer,
                'fanvue_return': bool(fanvue_customer and can_return and adult and reminder_ok),
                'link': telegram_link if primary == 'telegram' else bio_link,
                'telegram_link': telegram_link, 'bio_link': bio_link,
                'highlights': bool(eligible and spent and cfg.get('highlights_link') and reminder_ok),
                'remind': bool(allowed and adult and has_link and reminder_ok),
                'photo': bool(cfg.get('photos_enabled') and not user.get('photo_sent_at') and allowed and adult),
                'age_unknown': user.get('age_state', 'unknown') == 'unknown'}

    async def approval_state(self, key):
        """Read-only owner-card eligibility, without provider calls or receipts."""
        parts = str(key).split(':', 1)
        if len(parts) != 2:
            return 'superseded'
        action = await self.db.action(parts[1])
        if not action or action['igsid'] != parts[0]:
            return 'superseded'
        approved = (action.get('payload') or {}).get('approved_source_mid') == action.get('source_mid') and bool(action.get('source_mid'))
        if (action['state'] in ('ready', 'sending', 'sent', 'uncertain')
                or approved and action['state'] in ('pending', 'leased')):
            return 'sent'  # Already approved; never offer approval a second time.
        if action['state'] != 'approval' or not in_window(action.get('source_at')):
            return 'superseded'
        user = await self.db.user(parts[0]) or {}
        if (user.get('human_takeover') or not user.get('ai_enabled', True)
                or user.get('last_source_mid') != action['source_mid']):
            return 'superseded'
        cfg = await self.db.settings()
        if not cfg.get('enabled') or not cfg.get('connected') or cfg.get('reply_mode') == 'off':
            return 'paused'
        return 'awaiting'

    async def approve(self, key, text):
        parts = str(key).split(':', 1)
        if len(parts) != 2:
            return False
        action = await self.db.action(parts[1])
        if not action or action['state'] != 'approval' or action['igsid'] != parts[0] or not in_window(action.get('source_at')):
            return False
        cfg = await self.db.settings()
        user = await self.db.user(parts[0]) or {}
        if (not cfg.get('enabled') or not cfg.get('connected') or cfg.get('reply_mode') == 'off'
                or user.get('human_takeover') or not user.get('ai_enabled', True) or user.get('last_source_mid') != action['source_mid']):
            return False
        return bool(await self.db.change_action(action, {'state': 'ready', 'text': text,
            'payload': {**action['payload'], 'approved_source_mid': action['source_mid']}}, state='approval'))
