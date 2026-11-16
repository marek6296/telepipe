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


class InstagramDelivery:
    def __init__(self, db, agent):
        self.db, self.agent = db, agent
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

    async def ingest(self, raw, cfg, bootstrap=False):
        chat = api.rozober(raw, cfg['ig_user_id'])
        igsid, messages = chat['igsid'], chat['spravy']
        if not igsid or not messages:
            return
        user = await self.db.ensure_user(igsid, chat['username'])
        known = await self.db.known_mids(igsid)
        processed = await self.db.processed_mids(igsid)
        sent_actions = await self.db.actions(igsid=f'eq.{igsid}', state='in.(sent,sending,uncertain)', order='created_at.desc', limit='100')
        own_mids = {a.get('provider_id') for a in sent_actions if a.get('provider_id')}
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
                elif stamp:
                    await self.db.rpc('record_manual', key=message['mid'], igsid=igsid,
                        occurred=stamp.isoformat(), text=message['content'], photo=bool(message.get('has_image')),
                        account=cfg['ig_user_id'])
                    completed = parse_time(cfg.get('sync_completed_at'))
                    if not bootstrap and completed and stamp > completed:
                        await self.db.cancel_actions(igsid, 'manual_reply')
                        await self.db.update_user(igsid, {'human_takeover': True})
                        user['human_takeover'] = True
            await self.db.mark_message_effects(message['mid'])
        last = messages[-1]
        incoming = next((m for m in reversed(messages) if m['role'] == 'user'), None)
        if incoming:
            patch = {'last_incoming_at': (parse_time(incoming.get('created_time')).isoformat() if parse_time(incoming.get('created_time')) else None), 'last_source_mid': last['mid']}
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
        watermark = parse_time(cfg.get('replies_started_at'))
        if (bootstrap or not cfg.get('enabled') or cfg.get('reply_mode') == 'off' or not watermark
                or not source or source < watermark or not in_window(source)
                or user.get('human_takeover') or not user.get('ai_enabled', True)
                or (user.get('no_initiate') and not direct_request(last['content']))):
            return
        kind = last.get('kind', 'dm')
        if kind == 'unknown' or (kind == 'reaction' and not cfg.get('reactions_enabled')):
            return
        due = choose_due(kind, source, f'{self.db.model_id}:{last["mid"]}',
                         active=bool(parse_time(user.get('last_reply_at')) and utcnow()-parse_time(user['last_reply_at']) < timedelta(minutes=15)))
        # Queue uses provider time and deterministic delay; retries never reroll it.
        await self.db.rpc('enqueue', key=f'{cfg["ig_user_id"]}:{kind}:{last["mid"]}', kind=kind,
            igsid=igsid, target=chat['id'], source_mid=last['mid'], source_at=source.isoformat(),
            due=due.isoformat(), expires=(source+timedelta(hours=24)).isoformat(), payload={'account_id': cfg['ig_user_id'], 'requested_reply': direct_request(last['content'])})

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

    async def process_one(self, cfg):
        action = await self.db.rpc('claim')
        if not action:
            return
        # No sending outside the shared local day. The test exception is scoped to
        # one platform ID, expires, and never skips Meta, quota or operator gates.
        behavior = Behavior.from_row(await self.db.behavior())
        local = utcnow().astimezone(ZoneInfo(behavior.active_tz))
        block, _ = await self.db.hub.day(local, den.Rozvrh.from_row(await self.db.schedule()))
        testing = (action['igsid'] and cfg.get('test_igsid') == action['igsid']
                   and parse_time(cfg.get('test_until')) and parse_time(cfg['test_until']) > utcnow())
        if not testing and (not block or not in_active_window(local, behavior.active_start_min, behavior.active_end_min)):
            await self.defer(action, 'sleeping')
            return
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
                await self.ingest(raw, cfg)
                user = await self.db.user(action['igsid']) or {}
                current = await self.db.action(action['id'])
                if not current or current['state'] != 'leased':
                    return
                if cfg['reply_mode'] == 'semi' and not action['payload'].get('approved_source_mid'):
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
                    # Versioned conversation key: an old card cannot approve a new message.
                    changed = await self.db.change_action(action, {'state': 'approval', 'lease_until': None})
                    if changed:
                        import prehlad
                        ok = await self.agent._control.post_approval(channel='instagram', conv_key=f'{action["igsid"]}:{action["id"]}',
                            display_name=user.get('username') or action['igsid'], incoming_preview=prehlad.blok_rozhovoru(history),
                            suggestions=proposals, hint='Approval queues this exact reply; current window, schedule and limits still apply.')
                        if not ok:
                            await self.db.change_action(action, {'state': 'pending', 'due_at': (utcnow()+timedelta(minutes=15)).isoformat()}, state='approval')
                    return
                if action['kind'] == 'reaction':
                    text, link, reminder = '', False, False
                else:
                    if action['kind'] == 'photo':
                        current_offer = await self.offer_state(cfg, user)
                        if not current_offer['photo']:
                            await self.db.change_action(action, {'state': 'blocked', 'reason': 'photo_no_longer_allowed'})
                            return
                    raw_text = '[[PHOTO]]' if action['kind'] == 'photo' else action.get('text') if action['payload'].get('approved_source_mid') else await self.agent._napis(user, action['igsid'], cfg)
                    from instagram_interactions import prepare_response
                    offer = await self.offer_state(cfg, user)
                    prepared = prepare_response(raw_text or '', cfg, offer)
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
            if not text and action['kind'] not in ('reaction', 'photo'):
                await self.db.change_action(action, {'state': 'skipped', 'reason': 'empty_or_disallowed_response'})
                return
            # Final remote freshness read after generation. DB reservation follows immediately.
            if action['kind'] != 'comment':
                fresh = api.rozober(await asyncio.to_thread(api.conversation, cfg['access_token'], action['target_id']), cfg['ig_user_id'])
                latest = fresh['spravy'][-1] if fresh['spravy'] else {}
                if latest.get('mid') != action['source_mid'] or latest.get('role') != 'user':
                    await self.db.change_action(action, {'state': 'cancelled', 'reason': 'remote_context_changed'})
                    return
            correction = {}
            if action['kind'] == 'dm' and cfg.get('typo_enabled') and not action['payload'].get('approved_source_mid') and not link and not reminder:
                from instagram_interactions import small_typo
                text, correction = small_typo(text, action['id'])
            reserved = await self.db.rpc('reserve', action=action['id'], lease=action['lease_token'], text=text, link=link, reminder=reminder)
            if not reserved.get('ok'):
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
                if link or reminder:
                    await self.db.hub.record_invite('instagram', action['igsid'],
                        'telegram' if cfg.get('funnel_target') == 'telegram' else 'fanvue', scope=cfg['ig_user_id'])
        except api.InstagramError as exc:
            await self.defer(action, f'refresh_meta_{exc.kod}')
            await self.provider_error(exc)

    async def offer_state(self, cfg, user):
        from conversation_policy import allowed_destination, day_key
        restrictions = await self.db.hub.restrictions('instagram', user.get('igsid', ''), cfg['ig_user_id'])
        allowed = not (user.get('no_links') or user.get('no_initiate') or restrictions.get('no_links')
                       or restrictions.get('no_initiate') or restrictions.get('age_state') == 'minor_or_conflicting')
        if await self.db.hub.linked('instagram', user.get('igsid', ''), 'fanvue', cfg['ig_user_id']):
            allowed = False
        adult = user.get('age_state') in ('adult_self_declared', 'adult_platform_verified')
        links = await self.db.actions(contains_link='eq.true', reserved_at='not.is.null', order='reserved_at.desc', limit='100')
        recent = [a for a in links if parse_time(a['reserved_at']) and utcnow()-parse_time(a['reserved_at']) < timedelta(hours=24)]
        today = [a for a in links if parse_time(a['reserved_at']) and day_key(parse_time(a['reserved_at'])) == day_key(utcnow())]
        budget = len(recent) < 2 and len(today) < 2 and not any(utcnow()-parse_time(a['reserved_at']) < timedelta(hours=4) for a in recent)
        has_link = bool(user.get('link_sent_at'))
        reminder_ok = not parse_time(user.get('last_reminder_at')) or utcnow()-parse_time(user['last_reminder_at']) >= timedelta(days=1)
        return {'link': bool(allowed and adult and budget and not has_link and allowed_destination(cfg.get('funnel_target', ''), cfg)),
                'highlights': bool(allowed and adult and not has_link and not budget and cfg.get('highlights_link') and reminder_ok),
                'remind': bool(allowed and adult and has_link and reminder_ok),
                'photo': bool(cfg.get('photos_enabled') and not user.get('photo_sent_at') and allowed and adult),
                'age_unknown': user.get('age_state', 'unknown') == 'unknown'}

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
