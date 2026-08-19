"""Telegram login riadený z webu — fronta `tg_login_jobs`.

Next.js MTProto nevie, Telethon žije len tu. Wizard preto zapíše do fronty
job a worker ho v tomto polleri dotiahne do konca. Priebeh (stĺpec `phase`):

    send_code   ─ worker: connect + send_code_request ─→ code_sent
    code_sent   ─ klient doplní code_enc              ─→ verify_code
    verify_code ─ worker: sign_in(code)               ─→ done
                                                      ─→ need_password (2FA)
                                                      ─→ code_sent (zlý kód)
    need_password  ─ klient doplní password_enc       ─→ verify_password
    verify_password ─ worker: sign_in(password=…)     ─→ done
                                                      ─→ need_password (zlé heslo)
    ktorákoľvek fáza + chyba/TTL                      ─→ error

Tajomstvá: `api_hash_enc`, `code_enc`, `password_enc` a medzistav klienta
(`tmp_session_enc`) šifruje web tým istým `ENCRYPTION_KEY` ako worker
(`crypto.py`, formát nonce:ct:tag). Po každom pokuse worker maže kód aj heslo,
pri terminálnom stave (done/error/TTL) všetky citlivé stĺpce — v DB nemá nič
z toho prežiť dlhšie, než je nevyhnutné.

Zápis výsledku robí VÝHRADNE worker: klient na `models.tg_session_enc` ani
`tg_api_hash` nemá grant (migrácia 007), service key RLS obchádza.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    RPCError,
    SessionPasswordNeededError,
)

from crypto import CryptoError, decrypt, encrypt

log = logging.getLogger(__name__)

# Fázy, v ktorých je na ťahu worker.
ACTIONABLE_PHASES = ("send_code", "verify_code", "verify_password")
# Fázy, v ktorých job čaká na používateľa — worker im stráži len TTL.
WAITING_PHASES = ("code_sent", "need_password")
# Ťaháme oboje jedným dotazom: čakajúce joby treba po expirácii tiež upratať.
PENDING_PHASES = ("send_code", "code_sent", "verify_code", "need_password",
                  "verify_password")

_BATCH = 50

# Po každom pokuse: kód aj heslo sú jednorazové.
_WIPE_ATTEMPT = {"code_enc": "", "password_enc": ""}
# Terminálny stav: v riadku nesmie ostať nič citlivé.
_WIPE_ALL = {**_WIPE_ATTEMPT, "tmp_session_enc": "", "phone_code_hash": "",
             "api_hash_enc": ""}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _telethon_client(session: str, api_id: int, api_hash: str):
    """Default factory. Import je vnútri, nech sa dá poller testovať bez Telethonu."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    return TelegramClient(StringSession(session or ""), api_id, api_hash)


def _expired(job: Dict[str, Any], now: datetime.datetime) -> bool:
    raw = (job.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        ts = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        # Nečitateľný timestamp radšej neexpirujeme — TTL nie je dôvod stratiť job.
        log.warning("login job %s: nečitateľné expires_at %r", job.get("id"), raw)
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts < now


def _error_code(exc: BaseException) -> str:
    """`ApiIdInvalidError` → `api_id_invalid` — hláška pre wizard, stabilná pre UI."""
    name = type(exc).__name__
    if name.endswith("Error"):
        name = name[: -len("Error")]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower() or "rpc_error"


async def _patch_job(transport, job: Dict[str, Any], body: Dict[str, Any]) -> None:
    await transport._patch(
        "/tg_login_jobs",
        {"id": f"eq.{job['id']}"},
        {**body, "updated_at": _now().isoformat()},
    )


async def _fail(transport, job: Dict[str, Any], error: str) -> None:
    log.warning("login job %s (model %s): %s", job.get("id"), job.get("model_id"), error)
    await _patch_job(transport, job, {"phase": "error", "error": error, **_WIPE_ALL})


async def _safe_disconnect(client) -> None:
    try:
        await client.disconnect()
    except Exception:  # noqa: BLE001 — zlyhaný disconnect nesmie prepísať výsledok
        log.debug("login: disconnect zlyhal", exc_info=True)


async def _model_row(transport, model_id: str) -> Dict[str, Any]:
    rows = await transport._get(
        "/models",
        {"id": f"eq.{model_id}", "select": "tg_api_id,status,status_reason", "limit": "1"},
    )
    return rows[0] if rows else {}


async def _finish(transport, key: str, job: Dict[str, Any], client, api_hash: str,
                  me=None) -> None:
    """Zapíše hotovú session do `models` a job uzavrie ako `done`."""
    model_id = job["model_id"]
    row = await _model_row(transport, model_id)

    body: Dict[str, Any] = {
        "tg_session_enc": encrypt(client.session.save() or "", key),
        # TenantConfig číta tg_api_hash v plaintexte (patrí k api_id, nie je to tajomstvo
        # na úrovni session) — šifrovaný je len v jobe, kým ide cez klientský zápis.
        "tg_api_hash": api_hash,
        "updated_at": _now().isoformat(),
        # Odtiaľto sa počíta rozbeh stropov. Čerstvé číslo jazdí prvý deň na
        # štvrtine, do týždňa sa dostane na plný výkon — pre Telegram je nový
        # účet na plnom strope oveľa podozrivejší než zabehnutý s tým istým
        # objemom. Zapisuje sa pri KAŽDOM prihlásení: po výmene čísla alebo
        # po odvolanej session ide účet na Telegrame znova ako nový.
        "tg_connected_at": _now().isoformat(),
    }
    api_id = job.get("api_id")
    if api_id and int(api_id) != (row.get("tg_api_id") or 0):
        # Session je viazaná na api_id — nechať v modeli starú hodnotu by ju rozbilo.
        body["tg_api_id"] = int(api_id)
    if row.get("status") == "error" and row.get("status_reason") == "session_revoked":
        # `set_model_status` z tohto stavu na active neprepne (migrácia 007) —
        # po úspešnom prihlásení blok uvoľníme, nech vie klient kliknúť Activate.
        body["status"] = "draft"
        body["status_reason"] = ""

    await transport._patch("/models", {"id": f"eq.{model_id}"}, body)
    await _patch_job(transport, job, {"phase": "done", "error": "", **_WIPE_ALL})
    log.info("login job %s: model %s prihlásený ako %s", job.get("id"), model_id,
             getattr(me, "username", None) or getattr(me, "id", "?"))


async def _send_code(transport, key: str, factory: Callable, job: Dict[str, Any]) -> None:
    api_hash = decrypt(job.get("api_hash_enc") or "", key)
    client = factory("", int(job["api_id"]), api_hash)
    try:
        await client.connect()
        sent = await client.send_code_request(job.get("phone") or "")
        await _patch_job(transport, job, {
            "phase": "code_sent",
            "phone_code_hash": getattr(sent, "phone_code_hash", "") or "",
            # Medzistav klienta — sign_in musí bežať nad tým istým auth key.
            "tmp_session_enc": encrypt(client.session.save() or "", key),
            "error": "",
            **_WIPE_ATTEMPT,
        })
        log.info("login job %s: kód odoslaný", job.get("id"))
    finally:
        await _safe_disconnect(client)


async def _verify_code(transport, key: str, factory: Callable, job: Dict[str, Any]) -> None:
    api_hash = decrypt(job.get("api_hash_enc") or "", key)
    code = decrypt(job.get("code_enc") or "", key)
    tmp = decrypt(job["tmp_session_enc"], key) if job.get("tmp_session_enc") else ""

    client = factory(tmp, int(job["api_id"]), api_hash)
    try:
        await client.connect()
        try:
            me = await client.sign_in(
                phone=job.get("phone") or "",
                code=code,
                phone_code_hash=job.get("phone_code_hash") or "",
            )
        except SessionPasswordNeededError:
            # 2FA: kód sedel, klient si drží stav — pýtame cloud heslo.
            await _patch_job(transport, job, {
                "phase": "need_password",
                "tmp_session_enc": encrypt(client.session.save() or "", key),
                "error": "",
                **_WIPE_ATTEMPT,
            })
            return
        except PhoneCodeInvalidError:
            # Preklep — ten istý kód sa dá poslať znova, nový netreba.
            # `tmp_session_enc` a `phone_code_hash` preto zámerne ostávajú.
            await _patch_job(transport, job, {
                "phase": "code_sent", "error": "invalid_code", **_WIPE_ATTEMPT,
            })
            return
        await _finish(transport, key, job, client, api_hash, me)
    finally:
        await _safe_disconnect(client)


async def _verify_password(transport, key: str, factory: Callable,
                           job: Dict[str, Any]) -> None:
    api_hash = decrypt(job.get("api_hash_enc") or "", key)
    password = decrypt(job.get("password_enc") or "", key)
    tmp = decrypt(job["tmp_session_enc"], key) if job.get("tmp_session_enc") else ""

    client = factory(tmp, int(job["api_id"]), api_hash)
    try:
        await client.connect()
        try:
            me = await client.sign_in(password=password)
        except PasswordHashInvalidError:
            await _patch_job(transport, job, {
                "phase": "need_password", "error": "invalid_password", **_WIPE_ATTEMPT,
            })
            return
        await _finish(transport, key, job, client, api_hash, me)
    finally:
        await _safe_disconnect(client)


_HANDLERS = {
    "send_code": _send_code,
    "verify_code": _verify_code,
    "verify_password": _verify_password,
}


async def handle_job(transport, key: str, factory: Callable, job: Dict[str, Any]) -> None:
    """Jeden job. Známe (trvalé) chyby zapíše do jobu, prechodné pustí vyššie."""
    try:
        await _HANDLERS[job["phase"]](transport, key, factory, job)
    except FloodWaitError as exc:
        # Telegram rate-limit býva v hodinách až dňoch — wizard musí povedať koľko.
        await _fail(transport, job, f"flood_wait_{int(getattr(exc, 'seconds', 0) or 0)}")
    except CryptoError:
        log.exception("login job %s: dešifrovanie zlyhalo", job.get("id"))
        await _fail(transport, job, "decrypt_failed")
    except RPCError as exc:
        # Zamietnutie z Telegramu (zlý api_id, zablokované číslo, expirovaný kód…)
        # je trvalé — opakovanie nepomôže, nech to klient vidí hneď.
        await _fail(transport, job, _error_code(exc))
    # Ostatné (sieť, Supabase, bug) idú vyššie: job ostáva vo fronte a skúsi sa
    # v ďalšom cykle, TTL ho aj tak do 10 minút uprace.


async def poll_once(transport, encryption_key: str,
                    client_factory: Optional[Callable] = None,
                    now: Optional[datetime.datetime] = None) -> int:
    """Jeden prechod frontou. Vracia počet jobov, s ktorými sa niečo stalo.

    Nikdy nehádže: pád jedného jobu (aj neočakávaný) nesmie zastaviť ostatné
    ani zhodiť background task v `main.py`.
    """
    factory = client_factory or _telethon_client
    now = now or _now()

    jobs: List[Dict[str, Any]] = await transport._get("/tg_login_jobs", {
        "select": "*",
        "phase": f"in.({','.join(PENDING_PHASES)})",
        "order": "id.asc",
        "limit": str(_BATCH),
    })

    handled = 0
    for job in jobs:
        try:
            if _expired(job, now):
                # TTL: kód z SMS aj tak neplatí, tajomstvá von z DB.
                await _patch_job(transport, job,
                                 {"phase": "error", "error": "expired", **_WIPE_ALL})
                log.info("login job %s: expiroval", job.get("id"))
            elif job.get("phase") in ACTIONABLE_PHASES:
                await handle_job(transport, encryption_key, factory, job)
            else:
                continue  # čaká na používateľa
            handled += 1
        except Exception:  # noqa: BLE001 — jeden pokazený job nesmie zabiť ostatné
            log.exception("login job %s: pokus zlyhal — skúsim v ďalšom cykle",
                          job.get("id"))
    return handled
