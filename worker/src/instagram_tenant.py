"""Instagram tabuľky jednej modelky.

Rovnaká úloha ako `fanvue_tenant.TenantFanvueDb`, len pre tretiu platformu:
každý dotaz nesie `model_id`, aby sa dve modelky nikdy nevideli navzájom.

TOKEN SA DEŠIFRUJE AŽ TU, na hranici čítania. Von ide čistý text, ktorý ide
rovno do volania Instagramu — nikde inde v procese nemá čo robiť.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from crypto import decrypt

log = logging.getLogger(__name__)

INSTAGRAM = "/instagram"
IG_USERS = "/ig_users"
IG_MESSAGES = "/ig_messages"
IG_COMMENTS = "/ig_comments"
PERSONA = "/persona"
BEHAVIOR = "/behavior"


class TenantInstagramDb:
    """Instagram dáta jednej modelky. Rozhranie kopíruje `TenantFanvueDb`."""

    def __init__(self, transport, model_id: str, encryption_key: str) -> None:
        self._t = transport
        self.model_id = model_id
        from conversation_hub import ConversationHub
        self.hub = ConversationHub(transport, model_id)
        self._key = encryption_key

    @property
    def _mine(self) -> str:
        """Hodnota filtra `model_id` — píše sa v každom dotaze, nech je to vidieť."""
        return f"eq.{self.model_id}"

    async def _get(self, path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        return await self._t._get(path, params)

    async def _patch(self, path: str, params: Dict[str, str], body: Dict[str, Any]) -> None:
        await self._t._patch(path, params, body)

    async def _post(self, path: str, body: Any, upsert: bool = False) -> None:
        await self._t._post(path, body, upsert=upsert)

    # ---------- pripojenie a nastavenia ----------

    async def settings(self) -> Dict[str, Any]:
        """Riadok `instagram` aj s dešifrovaným tokenom.

        Prázdny slovník znamená „modelka Instagram nemá" — nie chybu. Volajúci
        na to reaguje tak, že agenta ani nespustí.
        """
        rows = await self._get(INSTAGRAM, {"model_id": self._mine, "select": "*"})
        if not rows:
            return {}
        row = dict(rows[0])
        row["access_token"] = self._token(row.pop("access_token_enc", ""))
        return row

    def _token(self, sealed: Any) -> str:
        """Dešifruje token; poškodený nezhodí agenta.

        Prázdny reťazec znamená „nemáme token" a agent sa v tom kole ani
        nespustí — to je lepšie než pád v strede kola.
        """
        text = str(sealed or "")
        if not text:
            return ""
        try:
            return decrypt(text, self._key)
        except Exception:  # noqa: BLE001 - zlý kľúč nesmie zhodiť tenanta
            log.error("model %s: Instagram token sa nedá dešifrovať", self.model_id)
            return ""

    async def save(self, patch: Dict[str, Any]) -> None:
        await self._patch(INSTAGRAM, {"model_id": self._mine}, patch)

    # ---------- persona (spoločná so všetkými agentmi) ----------

    async def persona(self) -> Dict[str, Any]:
        rows = await self._get(PERSONA, {"model_id": self._mine, "select": "*"})
        return dict(rows[0]) if rows else {}

    async def behavior(self) -> Dict[str, Any]:
        rows = await self._get(BEHAVIOR, {"model_id": self._mine, "select": "*"})
        return dict(rows[0]) if rows else {}

    # ---------- ľudia ----------

    async def user(self, igsid: str) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            IG_USERS, {"model_id": self._mine, "igsid": f"eq.{igsid}", "select": "*"}
        )
        return dict(rows[0]) if rows else None

    async def ensure_user(self, igsid: str, username: str = "") -> Dict[str, Any]:
        existujuci = await self.user(igsid)
        if existujuci:
            # Meno sa mohlo medzitým objaviť (v prvej správe ho Instagram
            # nemusí dať) — doplní sa, ale nikdy sa neprepíše na prázdne.
            if username and username != existujuci.get("username"):
                await self.update_user(igsid, {"username": username})
                existujuci["username"] = username
            return existujuci

        await self._post(
            IG_USERS,
            {"model_id": self.model_id, "igsid": igsid, "username": username},
            upsert=True,
        )
        return (await self.user(igsid)) or {
            "model_id": self.model_id,
            "igsid": igsid,
            "username": username,
            "msg_count": 0,
            "pointed_count": 0,
        }

    async def update_user(self, igsid: str, patch: Dict[str, Any]) -> None:
        await self._patch(
            IG_USERS, {"model_id": self._mine, "igsid": f"eq.{igsid}"}, patch
        )

    # ---------- správy ----------

    async def known_mids(self, igsid: str, limit: int = 60) -> set:
        """Ktoré správy už v histórii máme.

        Konverzácie sa ťahajú opakovane, takže bez tohto by tá istá správa
        pribudla do histórie pri každom kole a modelka by na ňu odpovedala znova.
        """
        rows = await self._get(
            IG_MESSAGES,
            {
                "model_id": self._mine,
                "igsid": f"eq.{igsid}",
                "select": "mid",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
        return {str(r.get("mid") or "") for r in rows if r.get("mid")}

    async def processed_mids(self, igsid):
        rows = await self._get(IG_MESSAGES, {'model_id': self._mine, 'igsid': f'eq.{igsid}',
            'effects_applied': 'eq.true', 'select': 'mid', 'order': 'id.desc', 'limit': '100'})
        return {r['mid'] for r in rows}

    async def mark_message_effects(self, mid):
        await self._patch(IG_MESSAGES, {'model_id': self._mine, 'mid': f'eq.{mid}'}, {'effects_applied': True})

    async def latest_message_id(self, igsid):
        rows = await self._get('/social_contact_summaries', {'model_id': self._mine,
            'channel': 'eq.instagram', 'external_id': f'eq.{igsid}',
            'select': 'last_message_id', 'limit': '1'})
        return int(rows[0].get('last_message_id') or 0) if rows else 0

    async def preview_source(self, igsid):
        """Newest observed provider event, for read-only preview eligibility."""
        rows = await self._get(IG_MESSAGES, {'model_id': self._mine, 'igsid': f'eq.{igsid}',
            'select': 'mid,role', 'order': 'occurred_at.desc.nullslast,id.desc', 'limit': '1'})
        return rows[0] if rows else {}

    async def native_reply(self, igsid, account, occurred_at):
        return await self._t._rpc('social_native_reply', {
            'p_model': self.model_id, 'p_channel': 'instagram', 'p_external': igsid,
            'p_scope': account, 'p_occurred_at': occurred_at,
        })

    async def requeue_stale_approval(self, igsid, source_mid, source_message_id):
        return await self.rpc('requeue_stale_approval', igsid=igsid,
                              source_mid=source_mid, source_message_id=source_message_id)

    async def add_message(self, igsid: str, role: str, content: str, mid: str = "",
                          occurred_at=None, source='worker', metadata=None) -> None:
        from datetime import datetime, timezone
        # The provider timestamp is authoritative. Ingestion time never opens a window.
        await self._post(
            IG_MESSAGES,
            {
                "model_id": self.model_id,
                "igsid": igsid,
                "mid": mid,
                "role": role,
                "content": content[:4000],
                "occurred_at": occurred_at or (datetime.now(timezone.utc).isoformat() if source == 'worker' else None),
                "source": source,
                "metadata": metadata or {},
            },
        )

    async def recent_chats(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Posledné konverzácie pre menu control bota."""
        return await self._get(
            IG_USERS,
            {
                "model_id": self._mine,
                "select": "igsid,username,msg_count,human_takeover,last_incoming_at",
                "order": "last_incoming_at.desc.nullslast",
                "limit": str(limit),
            },
        )

    # ---------- komentáre ----------

    async def handled_comments(self, comment_ids: List[str]) -> set:
        """Ktoré z týchto komentárov už sú vybavené (odpovedané alebo preskočené).

        Bez toho by agent pri každom kole odpovedal pod ten istý komentár znova
        — Instagram odpoveď pod komentár nepovažuje za „prečítané".
        """
        ids = [str(i) for i in comment_ids if i]
        if not ids:
            return set()
        rows = await self._get(
            IG_COMMENTS,
            {
                "model_id": self._mine,
                "comment_id": f"in.({','.join(ids)})",
                "select": "comment_id",
            },
        )
        return {str(r.get("comment_id") or "") for r in rows}

    async def save_comment(self, row: Dict[str, Any]) -> None:
        await self._post(
            IG_COMMENTS,
            {
                "model_id": self.model_id,
                "comment_id": str(row.get("comment_id") or ""),
                "media_id": str(row.get("media_id") or ""),
                "username": str(row.get("username") or ""),
                "text": str(row.get("text") or "")[:2000],
                "reply_text": str(row.get("reply_text") or "")[:2000],
                "status": str(row.get("status") or "replied"),
            },
            upsert=True,
        )

    async def history(self, igsid: str, limit: int = 16) -> List[Dict[str, str]]:
        """Posledných `limit` správ, od najstaršej — v tvare pre LLM."""
        rows = await self._get(
            IG_MESSAGES,
            {
                "model_id": self._mine,
                "igsid": f"eq.{igsid}",
                "select": "role,content,occurred_at,metadata",
                "order": "occurred_at.desc.nullslast,id.desc",
                "limit": str(limit),
            },
        )
        return [
            {"role": str(r.get("role") or "user"), "content": str(r.get("content") or ""), "occurred_at": r.get("occurred_at"), "metadata": r.get("metadata") or {}}
            for r in reversed(rows)
        ]

    async def rpc(self, name, **args):
        return await self._t._rpc('instagram_' + name, {'p_model': self.model_id, **{'p_' + k: v for k, v in args.items()}})

    async def action(self, action_id):
        rows = await self._get('/instagram_actions', {'model_id': self._mine, 'id': f'eq.{action_id}', 'select': '*'})
        return rows[0] if rows else None

    async def change_action(self, action, patch, state='leased'):
        params = {'model_id': self._mine, 'id': f"eq.{action['id']}", 'state': f'eq.{state}'}
        payload = action.get('payload') or {}
        if payload.get('origin') == 'operator':
            params['payload->>command_id'] = 'eq.' + str(payload.get('command_id') or '')
        if state == 'leased':
            params['lease_token'] = f"eq.{action['lease_token']}"
        return await self._t._patch_returning('/instagram_actions', params, patch)

    async def cancel_actions(self, igsid='', reason='channel_off', *, through=None):
        params = {'model_id': self._mine, 'state': 'in.(pending,ready,approval,leased)'}
        if reason in ('channel_off', 'takeover', 'manual_reply', 'outbound_is_latest'):
            params['or'] = '(payload->>origin.is.null,payload->>origin.neq.operator)'
        if igsid:
            params['igsid'] = f'eq.{igsid}'
        if through is not None:
            params['source_at'] = 'lte.' + through
        await self._patch('/instagram_actions', params, {'state': 'cancelled', 'reason': reason})

    async def prepare_operator_action(self, command, target, source_mid, source_at):
        """Bind a single already-fenced command directly to a leased IG action."""
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from conversation_policy import parse_time
        now = datetime.now(timezone.utc)
        payload = {'origin': 'operator', 'command_id': command['id'],
                   'operator_operation': command['operation'],
                   'account_id': command['account_scope'], 'approved_source_mid': source_mid}
        if command['operation'] == 'approve':
            payload['approved_intent'] = command.get('approved_intent') or ''
        patch = {'state': 'leased', 'lease_token': str(uuid4()),
                 'lease_until': (now + timedelta(minutes=2)).isoformat(), 'text': command['text']}
        if command.get('pending_id'):
            rows = await self._get('/pending_replies', {'model_id': self._mine,
                'id': 'eq.' + command['pending_id'], 'decision_command_id': 'eq.' + command['id'],
                'status': 'eq.sent', 'select': 'conv_key'})
            if not rows or ':' not in rows[0]['conv_key']:
                return None
            action = await self.action(rows[0]['conv_key'].split(':', 1)[1])
            if not action or action['igsid'] != command['external_id'] or action['source_mid'] != source_mid:
                return None
            changed = await self.change_action(action, {**patch, 'payload': {**action['payload'], **payload}}, state='approval')
            return changed[0] if changed else None
        deferred_id = (command.get('result') or {}).get('deferred_action_id')
        if deferred_id:
            action = await self.action(deferred_id)
            if (not action or action['state'] != 'approval' or action.get('reserved_at')
                    or action['igsid'] != command['external_id'] or action['source_mid'] != source_mid
                    or (action.get('payload') or {}).get('command_id') != command['id']
                    or (action.get('payload') or {}).get('account_id') != command['account_scope']):
                return None
            changed = await self.change_action(action, {**patch, 'payload': {**action['payload'], **payload}}, state='approval')
            return changed[0] if changed else None
        stamp = parse_time(source_at)
        if not stamp:
            return None
        rows = await self._t._post('/instagram_actions', {
            'model_id': self.model_id, 'dedupe_key': 'social:' + command['id'],
            'kind': 'dm', 'igsid': command['external_id'], 'target_id': target,
            'source_mid': source_mid, 'source_at': stamp.isoformat(), 'due_at': now.isoformat(),
            'expires_at': (stamp + timedelta(hours=24)).isoformat(), 'payload': payload, **patch})
        return rows[0] if rows else None

    async def actions(self, **params):
        return await self._get('/instagram_actions', {'model_id': self._mine, 'select': '*', **params})

    async def schedule(self):
        rows = await self._get('/model_schedule', {'model_id': self._mine, 'select': '*'})
        return rows[0] if rows else {}

    async def sfw_photo(self):
        rows = await self._get('/photos', {'model_id': self._mine, 'active': 'eq.true', 'spicy': 'eq.false',
            'instagram_approved': 'eq.true', 'select': 'id,url,caption', 'order': 'sent_count.asc', 'limit': '1'})
        return rows[0] if rows else None
