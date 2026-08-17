"""Async prístup k tenantovým tabuľkám cez `SupabaseTransport`.

Oproti šablóne (jedna modelka = jedna schéma) tu všetkých šestnásť tabuliek
žije v `public` a rozlišuje ich stĺpec `model_id`. Jediné, čo drží tenantov od
seba, je preto tento súbor: **každé** čítanie má filter `model_id=eq.…`, každý
zápis nesie `model_id` v tele a každý update/delete filtruje na oboje. Chýbajúci
filter = únik dát medzi modelkami, nie „len" zlý výsledok.

Spojenie vlastní `main` (jeden transport na proces); `TenantDb` je tenká vrstva
nad ním, takže sa dá pre každú modelku vyrobiť a zahodiť bez nákladov.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from transport import SupabaseTransport

log = logging.getLogger(__name__)

PERSONA = "/persona"
USERS = "/dm_users"
MESSAGES = "/dm_messages"
SETTINGS = "/settings"
PHOTOS = "/photos"
PHOTO_SENDS = "/photo_sends"
VOICES = "/voices"
VOICE_SENDS = "/voice_sends"
FACTS = "/facts"
EPISODES = "/episodes"
LOOPS = "/open_loops"
CLAIMS = "/self_claims"
JUDGE_LOG = "/judge_log"
BEHAVIOR = "/behavior"
VOICE_CLIPS = "/voice_clips"
VOICE_JOBS = "/voice_jobs"

# Vyrobené hlasovky si necháme. Dnes preto, aby si ich majiteľ vedel v dashboarde
# vypočuť, a raz preto, že z nich bude zásoba, z ktorej sa dá siahnuť po
# hotovej, keď sadne do kontextu.
VOICE_BUCKET = "model-voices"


def _ts(value: Optional[str]) -> Optional[datetime]:
    """Časová značka z PostgREST na datetime. Nečitateľnú radšej ignoruj."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class TenantDb:
    def __init__(self, transport: SupabaseTransport, model_id: str) -> None:
        self._t = transport
        self.model_id = model_id

    @property
    def _mine(self) -> str:
        """Hodnota filtra `model_id` — píše sa v každom dotaze, nech je to vidieť."""
        return f"eq.{self.model_id}"

    @property
    def _client(self) -> httpx.AsyncClient:
        """Surový klient transportu — pre dotazy s hlavičkami (count, upsert do
        úložiska), ktoré sa cez `_get/_patch/_post` vyjadriť nedajú."""
        return self._t._client

    async def _get(self, path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        return await self._t._get(path, params)

    async def _patch(self, path: str, params: Dict[str, str], body: Dict[str, Any]) -> None:
        await self._t._patch(path, params, body)

    async def _post(self, path: str, body: Any, upsert: bool = False) -> List[Dict[str, Any]]:
        return await self._t._post(path, body, upsert=upsert)

    # ---------- persona ----------

    async def get_persona(self) -> Dict[str, Any]:
        rows = await self._get(PERSONA, {"model_id": self._mine, "select": "*"})
        return rows[0] if rows else {}

    async def set_persona_field(self, field: str, value: str) -> None:
        await self._patch(
            PERSONA, {"model_id": self._mine}, {field: value, "updated_at": _now_iso()}
        )

    # ---------- chovanie ----------

    async def get_behavior(self) -> Dict[str, Any]:
        rows = await self._get(BEHAVIOR, {"model_id": self._mine, "select": "*"})
        return rows[0] if rows else {}

    async def set_behavior_field(self, field: str, value: Any) -> None:
        await self._patch(
            BEHAVIOR, {"model_id": self._mine}, {field: value, "updated_at": _now_iso()}
        )

    # ---------- globálne nastavenia ----------

    async def is_paused(self) -> bool:
        rows = await self._get(SETTINGS, {"model_id": self._mine, "select": "ai_paused"})
        return bool(rows and rows[0].get("ai_paused"))

    async def set_paused(self, paused: bool) -> None:
        await self._patch(SETTINGS, {"model_id": self._mine}, {"ai_paused": paused})

    # ---------- užívatelia ----------

    async def get_user(self, tg_id: int) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            USERS, {"model_id": self._mine, "tg_id": f"eq.{tg_id}", "select": "*"}
        )
        return rows[0] if rows else None

    async def ensure_user(
        self,
        tg_id: int,
        username: Optional[str],
        first_name: Optional[str],
        lang: Optional[str],
    ) -> Dict[str, Any]:
        """Vytvorí užívateľa, ak neexistuje; inak osvieži meta údaje."""
        existing = await self.get_user(tg_id)
        meta = {"username": username, "first_name": first_name, "lang": lang}
        if existing:
            changed = {k: v for k, v in meta.items() if v and existing.get(k) != v}
            if changed:
                await self.update_user(tg_id, changed)
                existing.update(changed)
            return existing
        rows = await self._post(USERS, {"model_id": self.model_id, "tg_id": tg_id, **meta})
        return rows[0] if rows else {"model_id": self.model_id, "tg_id": tg_id, **meta}

    async def update_user(self, tg_id: int, patch: Dict[str, Any]) -> None:
        await self._patch(USERS, {"model_id": self._mine, "tg_id": f"eq.{tg_id}"}, patch)

    async def find_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "username": f"ilike.{username.lstrip('@')}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def wipe_conversation(self, tg_id: int) -> int:
        """Vymaže históriu a vynuluje stav jednej konverzácie.

        Slúži na testovanie: po tomto sa daný človek chová ako úplne nový.
        Vracia počet zmazaných správ.
        """
        before = await self.recent_messages(tg_id, 10_000)
        # Archív správ, záznamy o poslaných fotkách a hlasovkách — inak by po
        # vymazaní dostal iba tie, ktoré ešte nevidel, a testovať sa to nedá.
        #
        # A hlavne CELÁ pamäť. Kým sa mazali len správy, ostávali po nej fakty,
        # epizódy, sľuby aj tvrdenia — takže „úplne nový človek" si po prvej
        # správe pamätal, čím sa živí a čo si o sebe povedali. Na jednom
        # testovacom účte tak zostalo jedenásť tvrdení pri nula správach.
        for path in (MESSAGES, PHOTO_SENDS, VOICE_SENDS, FACTS, EPISODES, LOOPS, CLAIMS):
            r = await self._client.delete(
                path, params={"model_id": self._mine, "tg_id": f"eq.{tg_id}"}
            )
            r.raise_for_status()
        await self.update_user(
            tg_id,
            {
                "msg_count": 0,
                "funnel_stage": "cold",
                "summary": "",
                "summary_at_msg": 0,
                "style_note": "",
                "partner_name": "",
                "name_asked": False,
                "asked_topics": {},
                "used_gags": {},
                # `last_msg_id` sa NEVYNULUJE. Telegram si históriu drží aj po
                # vymazaní našej — a Reconciler by pri nule stiahol späť
                # posledných tridsať správ a odpovedal na ne, akoby prišli
                # teraz. Presne to sa stalo: po vyčistení chatu dorazilo dvanásť
                # starých správ naraz a vyzeralo to, že píše sama od seba.
                "link_sent_at": None,
                "link_push_count": 0,
                "paid": False,
                "human_takeover": False,
                "pending_reply": False,
                "reply_after": None,
                "notified": False,
                "last_incoming_at": None,
                "last_reply_at": None,
                "last_photo_at": None,
                "last_voice_at": None,
                "last_outreach_at": None,
                "outreach_silent": 0,
                "tidied_at": None,
            },
        )
        return len(before)

    async def links_sent_since(self, since_iso: str) -> int:
        """Koľko odkazov išlo od daného času — naprieč všetkými konverzáciami.

        Počíta sa z DB, nie z pamäte procesu, aby to prežilo restart na Railway.
        """
        r = await self._client.get(
            USERS,
            params={
                "model_id": self._mine,
                "link_sent_at": f"gte.{since_iso}",
                "select": "tg_id",
            },
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    async def active_chats(self, since_iso: str, limit: int = 200) -> List[int]:
        """Kto má práve otvorený rozhovor — jeho alebo jej správa je čerstvá.

        Berie sa aj jej odpoveď, nielen jeho správa: keď odpísala pred piatimi
        minútami a on ešte nereagoval, rozhovor beží a miesto je obsadené.
        """
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "tg_id",
                "or": f"(last_incoming_at.gte.{since_iso},last_reply_at.gte.{since_iso})",
                "limit": str(limit),
            },
        )
        return [int(r["tg_id"]) for r in rows if r.get("tg_id") is not None]

    async def people_since(self, since_iso: str) -> List[int]:
        """Komu z účtu odišla správa od daného času — zoznam tg_id.

        Samotný počet správ nestačí: tridsať správ dvom ľuďom je človek, ktorý
        sa rozpísal, kým tridsať správ tridsiatim ľuďom je obchôdzka. Práve to
        druhé je vzor, na ktorý Telegram reaguje.
        """
        rows = await self._get(
            MESSAGES,
            {
                "model_id": self._mine,
                "role": "eq.assistant",
                "created_at": f"gte.{since_iso}",
                "select": "tg_id",
                "limit": "2000",
            },
        )
        return [int(r["tg_id"]) for r in rows if r.get("tg_id") is not None]

    async def replies_since(self, since_iso: str) -> int:
        """Koľko správ z účtu odišlo od daného času — naprieč konverzáciami.

        Čítač v pamäti procesu je po každom deployi prázdny, takže sa hodinový
        strop dal reštartom vynulovať. Toto to prežije, lebo sa počíta z
        archívu odoslaných správ.
        """
        r = await self._client.get(
            MESSAGES,
            params={
                "model_id": self._mine,
                "role": "eq.assistant",
                "created_at": f"gte.{since_iso}",
                "select": "id",
            },
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    async def recent_conversations(self, limit: int = 10) -> List[Dict[str, Any]]:
        return await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "order": "last_incoming_at.desc.nullslast",
                "limit": str(limit),
            },
        )

    async def sessions_to_close(
        self, gap_hours: int = 6, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Sedenia, ktoré dozneli a ešte nie sú zapísané ako epizóda.

        Epizóda sa doteraz písala len vtedy, keď človek po dlhom tichu napísal
        znova — takže kto sa neozval, o tom nebol záznam. Naživo z toho vyšlo
        pol epizódy na konverzáciu a celá vrstva pamäte, po ktorej má ostať
        pocit „ona si ma pamätá", bola prakticky prázdna.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=gap_hours)
        ).isoformat()
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "last_incoming_at": f"lt.{cutoff}",
                "order": "last_incoming_at.desc",
                "limit": str(limit * 6),
            },
        )
        cakaju = [
            r for r in rows
            if int(r.get("msg_count") or 0) >= 3
            and not (r.get("episode_at") or "") >= (r.get("last_incoming_at") or "")
        ]
        return cakaju[:limit]

    async def pending_users(self) -> List[Dict[str, Any]]:
        return await self._get(
            USERS,
            {"model_id": self._mine, "pending_reply": "is.true", "select": "*", "limit": "50"},
        )

    async def outreach_candidates(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Ľudia, ktorých sa ráno oplatí osloviť — filtrovanie robí `outreach`."""
        return await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "order": "last_incoming_at.desc",
                "limit": str(limit),
                "last_incoming_at": "not.is.null",
            },
        )

    async def unanswered_users(
        self, limit: int = 50, stale_hours: int = 48
    ) -> List[Dict[str, Any]]:
        """Ľudia, ktorých posledná správa ostala bez odpovede.

        Nezávisí to na príznaku `pending_reply` — ten sa dá stratiť (pád workera
        v nesprávnom momente, ručný zásah v DB). Toto je sieť pod tým: porovná
        sa čas jeho poslednej správy s časom jej poslednej odpovede, takže sa
        nikto nestratí ani po restarte.

        Staré správy sa ale nechávajú tak. Reconciler po štarte správne
        rozhodne, že na štyri dni starú správu sa už neodpisuje — a táto sieť
        ho potom prebila a odpísala aj tak. Odpoveď na štyri dni starý pozdrav
        vyzerá horšie než žiadna.
        """
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "order": "last_incoming_at.desc",
                "limit": str(limit),
                "last_incoming_at": "not.is.null",
            },
        )
        hranica = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
        waiting = []
        for row in rows:
            if row.get("human_takeover") or not row.get("ai_enabled", True):
                continue
            incoming = _ts(row.get("last_incoming_at"))
            replied = _ts(row.get("last_reply_at"))
            if not incoming or incoming < hranica:
                continue
            if replied is None or replied < incoming:
                waiting.append(row)
        return waiting

    # ---------- správy ----------

    async def add_message(self, tg_id: int, role: str, content: str) -> None:
        await self._post(
            MESSAGES,
            {"model_id": self.model_id, "tg_id": tg_id, "role": role, "content": content},
        )

    async def recent_messages(self, tg_id: int, limit: int) -> List[Dict[str, Any]]:
        """Posledných `limit` správ v chronologickom poradí."""
        rows = await self._get(
            MESSAGES,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "role,content,created_at",
                "order": "id.desc",
                "limit": str(limit),
            },
        )
        return list(reversed(rows))

    # ---------- fakty ----------

    async def facts_for(self, tg_id: int) -> List[Dict[str, Any]]:
        return await self._get(
            FACTS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "*",
                "order": "id.asc",
                "limit": "200",
            },
        )

    async def apply_facts(self, tg_id: int, plan: Dict[str, Any]) -> None:
        """Append-only zápis: staré fakty sa neprepisujú, len odkladajú."""
        for fact_id in plan.get("confirms", []):
            await self._patch(
                FACTS,
                {"model_id": self._mine, "id": f"eq.{fact_id}"},
                {"last_confirmed": _now_iso()},
            )
        new_rows = [
            {"model_id": self.model_id, "tg_id": tg_id, "key": item["key"], "value": item["value"]}
            for item in plan.get("inserts", [])
        ]
        created = await self._post(FACTS, new_rows) if new_rows else []
        marker = created[0]["id"] if created else None
        for fact_id in plan.get("supersedes", []):
            await self._patch(
                FACTS, {"model_id": self._mine, "id": f"eq.{fact_id}"}, {"superseded_by": marker}
            )

    # ---------- epizódy a sľuby ----------

    async def add_episode(self, tg_id: int, episode: Dict[str, Any]) -> None:
        await self._post(EPISODES, {"model_id": self.model_id, "tg_id": tg_id, **episode})

    async def episodes_for(self, tg_id: int, limit: int = 4) -> List[Dict[str, Any]]:
        rows = await self._get(
            EPISODES,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "*",
                "order": "ended_at.desc",
                "limit": str(limit),
            },
        )
        return list(reversed(rows))

    async def open_loops(self, tg_id: int) -> List[Dict[str, Any]]:
        return await self._get(
            LOOPS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "closed_at": "is.null",
                "select": "*",
                "limit": "10",
            },
        )

    async def add_loop(self, tg_id: int, what: str) -> None:
        await self._post(LOOPS, {"model_id": self.model_id, "tg_id": tg_id, "what": what})

    async def close_loop(self, loop_id: int) -> None:
        await self._patch(
            LOOPS, {"model_id": self._mine, "id": f"eq.{loop_id}"}, {"closed_at": _now_iso()}
        )

    async def search_archive(self, tg_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fulltext nad celou históriou — archív prestáva byť mŕtvy náklad."""
        if not query.strip():
            return []
        rows = await self._t._rpc(
            "search_messages",
            {"p_model": self.model_id, "p_tg_id": tg_id, "p_query": query, "p_limit": limit},
        )
        return rows or []

    # ---------- čo o sebe natvrdila ----------

    async def self_claims(self, tg_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        return await self._get(
            CLAIMS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "*",
                "order": "said_at.desc",
                "limit": str(limit),
            },
        )

    async def add_self_claim(self, tg_id: int, claim: str) -> None:
        await self._post(CLAIMS, {"model_id": self.model_id, "tg_id": tg_id, "claim": claim})

    async def log_judge(self, tg_id: int, draft: str, fixed: str, reason: str) -> None:
        await self._post(JUDGE_LOG, {"model_id": self.model_id, "tg_id": tg_id,
                                     "draft": draft[:1000],
                                     "fixed": fixed[:1000], "reason": reason[:300]})

    async def tidy_facts(self, tg_id: int) -> int:
        """Nočné čistenie faktov. Soft-delete: staré sa označia, nikdy nemažú.

        Rieši to, čo sa do databázy dostalo predtým, než začali platiť uzavreté
        kľúče a zlučovanie podľa významu:

          * **okamihy uložené ako trvalé fakty** — „leží na gauči a pozerá
            seriál" bolo naživo zapísané pod štyrmi kľúčmi naraz. Ako fakt to
            neplatí ani o hodinu.
          * **tá istá vec pod dvoma kľúčmi** — `past_locations` aj
            `previous_locations` s rovnakou hodnotou. Zlučovanie porovnávalo
            kľúče, takže sa tie dva nikdy nestretli.
        """
        import facts as facts_mod
        import similar

        rows = await self.facts_for(tg_id)
        active = sorted(
            (f for f in rows if f.get("superseded_by") is None),
            key=lambda f: f["id"],
        )
        merged = 0
        ponechane: List[Dict[str, Any]] = []
        for fact in active:
            key, value = fact.get("key") or "", (fact.get("value") or "").strip()
            if not value or facts_mod.is_transient(key, value):
                # Okamih nemá čím nahradiť — odloží sa sám sebou, aby sa
                # zachovalo, že tam raz bol, ale do promptu už nešiel.
                await self._patch(
                    FACTS,
                    {"model_id": self._mine, "id": f"eq.{fact['id']}"},
                    {"superseded_by": fact["id"]},
                )
                merged += 1
                continue
            dvojnik = next(
                (f for f in ponechane if similar.same_idea(value, f["value"])), None
            )
            if dvojnik is not None:
                await self._patch(
                    FACTS,
                    {"model_id": self._mine, "id": f"eq.{dvojnik['id']}"},
                    {"superseded_by": fact["id"]},
                )
                ponechane.remove(dvojnik)
                merged += 1
            ponechane.append({"id": fact["id"], "value": value})
        await self.update_user(tg_id, {"tidied_at": _now_iso()})
        return merged

    # ---------- fotky ----------

    async def photo_library(self) -> List[Dict[str, Any]]:
        return await self._get(
            PHOTOS,
            {"model_id": self._mine, "select": "*", "active": "is.true", "order": "id.asc"},
        )

    async def photos_sent_to(self, tg_id: int) -> List[int]:
        """Fotky, ktoré už tento človek videl — od najnovšej.

        Na poradí záleží: podľa poslednej poslanej sa vyberá ďalšia z tej istej
        kolekcie, aby po fotke z postele neprišla fotka z párty.
        """
        rows = await self._get(
            PHOTO_SENDS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "photo_id,sent_at",
                "order": "sent_at.desc",
            },
        )
        return [int(r["photo_id"]) for r in rows]

    async def voice_library(self) -> List[Dict[str, Any]]:
        """Hlasovky pripravené na posielanie.

        Pevné políčka bez nahratého zvuku majú prázdne `url` — tie sa
        preskakujú, inak by sa modelka pokúsila poslať prázdnu nahrávku.
        """
        rows = await self._get(
            VOICES, {"model_id": self._mine, "active": "is.true", "select": "*", "order": "id"}
        )
        return [r for r in rows if (r.get("url") or "").strip()]

    async def voices_sent_to(self, tg_id: int) -> List[int]:
        rows = await self._get(
            VOICE_SENDS,
            {"model_id": self._mine, "tg_id": f"eq.{tg_id}", "select": "voice_id"},
        )
        return [int(r["voice_id"]) for r in rows]

    async def record_voice_send(self, voice_id: int, tg_id: int) -> None:
        """Zápis, že túto nahrávku už počul — druhýkrát ju nedostane."""
        # Zloženému PK (model_id, voice_id, tg_id) stačí PostgREST default —
        # `resolution=merge-duplicates` si konflikt odvodí z primárneho kľúča.
        await self._post(
            VOICE_SENDS,
            {"model_id": self.model_id, "voice_id": voice_id, "tg_id": tg_id},
            upsert=True,
        )
        await self._client.patch(
            VOICES,
            params={"model_id": self._mine, "id": f"eq.{voice_id}"},
            # Predtým sa sem zapisovala natvrdo jednotka, takže štatistika
            # hlasoviek ukazovala 1 aj po stovke odoslaní.
            json={"sent_count": await self._voice_count(voice_id)},
            headers={"Prefer": "return=minimal"},
        )

    async def _voice_count(self, voice_id: int) -> int:
        r = await self._client.get(
            VOICE_SENDS,
            params={"model_id": self._mine, "voice_id": f"eq.{voice_id}", "select": "tg_id"},
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    async def record_photo_send(self, photo_id: int, tg_id: int) -> None:
        """Zápis, že táto fotka už tomuto človeku odišla — druhýkrát nepôjde."""
        await self._post(
            PHOTO_SENDS,
            {"model_id": self.model_id, "photo_id": photo_id, "tg_id": tg_id},
            upsert=True,
        )
        await self._client.patch(
            PHOTOS,
            params={"model_id": self._mine, "id": f"eq.{photo_id}"},
            json={"sent_count": await self._photo_count(photo_id)},
        )

    async def _photo_count(self, photo_id: int) -> int:
        r = await self._client.get(
            PHOTO_SENDS,
            params={"model_id": self._mine, "photo_id": f"eq.{photo_id}", "select": "tg_id"},
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    # ---------- vyrobené hlasovky ----------

    async def upload_voice(self, path: str, data: bytes) -> str:
        """Uloží nahrávku do úložiska a vráti verejnú adresu.

        Prázdny reťazec = nepodarilo sa. Archív je bonus: keď zlyhá, hlasovka
        aj tak odíde klientovi, len ju majiteľ neuvidí v dashboarde.

        Cestu skladá volajúci a už je tenant-unikátna (`cfg.supabase_schema`
        == model_id), preto sa tu žiadna predpona nepridáva.
        """
        base = str(self._client.base_url).rsplit("/rest/v1", 1)[0]
        try:
            r = await self._client.post(
                f"{base}/storage/v1/object/{VOICE_BUCKET}/{path}",
                content=data,
                headers={"Content-Type": "audio/ogg", "x-upsert": "true"},
            )
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - archív nesmie zdržať odpoveď
            log.warning("Hlasovku sa nepodarilo uložiť (%s): %s", path, exc)
            return ""
        return f"{base}/storage/v1/object/public/{VOICE_BUCKET}/{path}"

    async def add_voice_clip(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            rows = await self._post(VOICE_CLIPS, {"model_id": self.model_id, **row})
        except Exception as exc:  # noqa: BLE001
            log.warning("Záznam o hlasovke sa nepodarilo zapísať: %s", exc)
            return None
        return rows[0] if rows else None

    async def voice_clips(self, limit: int = 60) -> List[Dict[str, Any]]:
        return await self._get(
            VOICE_CLIPS,
            {"model_id": self._mine, "select": "*", "order": "id.desc", "limit": str(limit)},
        )

    # ---------- fronta na ukážky z dashboardu ----------
    #
    # Worker na Railway nemá port — je to worker, nie web služba, takže HTTP
    # endpoint by znamenal prerobiť ju na web s doménou. Fronta v databáze to
    # celé obchádza: dashboard vloží riadok, worker ho spracuje a zapíše adresu
    # hotového súboru. Ako bonus je ukážka vyrobená presne tým istým reťazcom
    # ako ostrá hlasovka, takže sa nemôžu rozísť.

    async def pending_voice_job(self) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            VOICE_JOBS,
            {
                "model_id": self._mine,
                "status": "eq.pending",
                "select": "*",
                "order": "id.asc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def claim_voice_job(self, job_id: int) -> bool:
        """Označí prácu za rozrobenú. False = medzitým ju vzal niekto iný."""
        r = await self._client.patch(
            VOICE_JOBS,
            params={"model_id": self._mine, "id": f"eq.{job_id}", "status": "eq.pending"},
            json={"status": "working"},
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        return bool(r.json())

    async def finish_voice_job(self, job_id: int, url: str = "", error: str = "") -> None:
        await self._patch(
            VOICE_JOBS,
            {"model_id": self._mine, "id": f"eq.{job_id}"},
            {
                "status": "error" if error else "done",
                "url": url,
                "error": error[:300],
                "done_at": _now_iso(),
            },
        )

    async def add_voice_job(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self._post(VOICE_JOBS, {"model_id": self.model_id, **row})
        return rows[0] if rows else None

    # ---------- štatistika ----------

    async def stats(self) -> Dict[str, int]:
        async def count(params: Dict[str, str]) -> int:
            r = await self._client.get(
                USERS,
                params={"model_id": self._mine, **params, "select": "tg_id"},
                headers={"Prefer": "count=exact", "Range": "0-0"},
            )
            r.raise_for_status()
            return int(r.headers.get("content-range", "*/0").split("/")[-1])

        return {
            "users": await count({}),
            "warm": await count({"funnel_stage": "eq.warm"}),
            "link_sent": await count({"funnel_stage": "eq.link_sent"}),
            "converted": await count({"funnel_stage": "eq.converted"}),
            "takeover": await count({"human_takeover": "is.true"}),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
