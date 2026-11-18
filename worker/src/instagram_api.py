"""Instagram Graph API — čítanie konverzácií a odosielanie správ.

Unified Login používa graph.facebook.com a explicitné ID Instagram účtu.
/me je systémový používateľ, nie Instagram profil. Agent konverzácie polluje.

ČO HOVORÍ DOKUMENTÁCIA A ČO Z TOHO PLYNIE
-----------------------------------------
* Konverzáciu VŽDY začína fanúšik. „Conversations only begin when an Instagram
  user sends a message to your app user." Modelka teda nemá ako napísať prvá —
  a to je zhodou okolností presne to, čo od nej chceme.
* Na odpoveď je 24 hodín od jeho správy. Po nich sa dá odpovedať len s tagom
  pre ľudského operátora, čo pre automat nie je pravda — takže sa neodpovedá.
* Text správy je najviac 1000 BAJTOV (nie znakov). Emoji majú štyri bajty,
  takže „tisíc znakov" by bola tichá chyba.
* Z konverzácie sa dá vytiahnuť detail len o posledných dvadsiatich správach.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"
VERZIA = "v27.0"

# Strop dĺžky správy podľa dokumentácie. V BAJTOCH.
MAX_BAJTOV = 1000

# Okno na odpoveď od jeho poslednej správy.
OKNO_H = 24

# Koľko posledných správ z konverzácie má zmysel pýtať — Instagram detail
# starších než dvadsať aj tak nevráti.
HISTORIA = 20

# Koľko komentárov na príspevok sa pýta. Staršie než posledných pár desiatok
# aj tak nemá zmysel dobiehať — odpoveď týždeň po komentári pôsobí ako bot.
KOMENTARE_NA_PRISPEVOK = 25

# Odpoveď pod komentárom je verejná a má byť krátka. Instagram znesie viac,
# ale jedna veta pod príspevkom je to, čo píše človek.
MAX_BAJTOV_KOMENTAR = 300


class InstagramError(RuntimeError):
    """Čokoľvek, čo Instagram odmietol. Nesie aj kód, nech sa dá rozhodnúť."""

    def __init__(self, sprava: str, kod: int = 0, podtyp: str = "", http_status: int | None = None) -> None:
        super().__init__(sprava)
        self.kod = kod
        self.podtyp = podtyp
        self.http_status = http_status


def _volaj(url: str, data: Optional[Dict[str, Any]] = None, timeout: float = 20.0) -> Dict[str, Any]:
    """Jedno volanie. `data` = POST (JSON), inak GET."""
    telo = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        url,
        data=telo,
        headers={"Content-Type": "application/json"} if telo else {},
        method="POST" if telo else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as odpoved:
            return json.loads(odpoved.read().decode() or "{}")
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        surove = exc.read().decode(errors="replace")
        try:
            chyba = (json.loads(surove).get("error") or {})
        except json.JSONDecodeError:
            chyba = {}
        raise InstagramError(
            str(chyba.get("message") or surove)[:300],
            kod=int(chyba.get("code") or exc.code),
            podtyp=str(chyba.get("error_subcode") or ""),
            http_status=exc.code,
        ) from exc
    except Exception as exc:  # noqa: BLE001 - sieť
        raise InstagramError(str(exc)[:300]) from exc


def _url(cesta: str, token: str, **params: Any) -> str:
    params["access_token"] = token
    return f"{GRAPH}/{VERZIA}/{cesta.lstrip('/')}?{urllib.parse.urlencode(params)}"


def profil(token: str, account_id: str) -> Dict[str, Any]:
    """Kto sme. Slúži aj ako kontrola, či token ešte žije."""
    return _volaj(_url(account_id, token, fields="id,username,account_type"))


def konverzacie(token: str, limit: int = 25, *, account_id: str) -> List[Dict[str, Any]]:
    """Konverzácie aj so správami, zoradené od najnovšie aktívnej.

    Správy sa ťahajú rovno v jednom dotaze (`messages{...}`) — inak by to bolo
    jedno volanie na konverzáciu a ešte jedno na každú správu.
    """
    out = _volaj(
        _url(
            f"{account_id}/conversations",
            token,
            platform="instagram",
            fields=f"id,updated_time,participants,messages.limit({HISTORIA})"
                   "{id,created_time,from,to,message}",
            limit=limit,
        )
    )
    return list(out.get("data") or [])


def posli_text(token: str, igsid: str, text: str, *, account_id: str) -> Dict[str, Any]:
    """Pošle text. Vracia odpoveď Instagramu (obsahuje `message_id`)."""
    orezany = orez(text)
    if not orezany:
        raise InstagramError("prázdna správa")
    return _volaj(
        _url(f"{account_id}/messages", token),
        {"recipient": {"id": str(igsid)}, "message": {"text": orezany}},
    )


def prispevky_s_komentarmi(token: str, limit: int = 8, *, account_id: str) -> List[Dict[str, Any]]:
    """Posledné príspevky aj s komentármi — JEDNÝM volaním.

    Komentáre sa ťahajú vnorene (`comments.limit(...)`) a s nimi aj odpovede
    pod nimi: z nich sa pozná, či už pod komentárom niečo napísala (ručne
    v appke alebo minule agent). Volanie na každý príspevok zvlášť by pri
    pollovaní zjedlo limit API skôr než konverzácie.
    """
    out = _volaj(
        _url(
            f"{account_id}/media",
            token,
            fields=(
                "id,caption,timestamp,"
                f"comments.limit({KOMENTARE_NA_PRISPEVOK})"
                "{id,text,timestamp,username,from,replies{id,username,from}}"
            ),
            limit=limit,
        )
    )
    return list(out.get("data") or [])


def odpovedz_na_komentar(token: str, comment_id: str, text: str) -> Dict[str, Any]:
    """Verejná odpoveď pod komentárom. Vracia odpoveď Instagramu (`id`)."""
    orezany = orez(text, MAX_BAJTOV_KOMENTAR)
    if not orezany:
        raise InstagramError("prázdna odpoveď")
    return _volaj(_url(f"{comment_id}/replies", token), {"message": orezany})


def rozober_komentare(prispevky: List[Dict[str, Any]], moje_id: str, moje_meno: str = "") -> List[Dict[str, Any]]:
    """Príspevky z API → komentáre cudzích ľudí, pod ktorými ešte nie je jej odpoveď.

    Jej vlastné komentáre sa vynechávajú (inak by si odpovedala sama sebe) a
    rovnako komentáre, pod ktorými už jej odpoveď je — tie vybavila ručne
    v appke a druhá odpoveď by vyzerala ako bot.
    """
    ja_id = str(moje_id or "")
    ja_meno = str(moje_meno or "").lower()

    def je_moj(polozka: Dict[str, Any]) -> bool:
        kto = polozka.get("from") or {}
        if ja_id and str(kto.get("id") or "") == ja_id:
            return True
        meno = str(polozka.get("username") or kto.get("username") or "").lower()
        return bool(ja_meno) and meno == ja_meno

    out: List[Dict[str, Any]] = []
    for prispevok in prispevky or []:
        for komentar in ((prispevok.get("comments") or {}).get("data")) or []:
            if not komentar.get("id") or je_moj(komentar):
                continue
            odpovede = ((komentar.get("replies") or {}).get("data")) or []
            if any(je_moj(o) for o in odpovede):
                continue
            text = str(komentar.get("text") or "").strip()
            if not text:
                continue
            kto = komentar.get("from") or {}
            out.append(
                {
                    "comment_id": str(komentar["id"]),
                    "media_id": str(prispevok.get("id") or ""),
                    "caption": str(prispevok.get("caption") or "")[:300],
                    "username": str(komentar.get("username") or kto.get("username") or ""),
                    "text": text,
                    "created_time": komentar.get("timestamp"),
                }
            )
    return out


def orez(text: str, strop: int = MAX_BAJTOV) -> str:
    """Skráti na povolený počet BAJTOV, nie znakov.

    Emoji zaberá štyri bajty, takže počítanie znakov by bola tichá chyba —
    správa by prešla u nás a odmietol by ju Instagram. Reže sa na hranici slova
    a nikdy nie uprostred viacbajtového znaku.
    """
    surove = (text or "").strip()
    if len(surove.encode("utf-8")) <= strop:
        return surove
    orezane = surove.encode("utf-8")[:strop].decode("utf-8", errors="ignore")
    medzera = orezane.rfind(" ")
    if medzera > strop // 2:
        orezane = orezane[:medzera]
    return orezane.rstrip()


def _cas(hodnota: Any) -> Optional[datetime]:
    if not hodnota:
        return None
    text = str(hodnota)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def v_okne(posledna_jeho: Any, teraz: Optional[datetime] = None, hodin: int = OKNO_H) -> bool:
    """Smie sa ešte odpovedať?

    Po dvadsiatich štyroch hodinách sa dá odpovedať už len s tagom pre ľudského
    operátora. Ten je vyhradený pre skutočného človeka, takže ho automat použiť
    nesmie — a odpoveď po okne by aj tak Instagram odmietol.
    """
    kedy = _cas(posledna_jeho)
    if kedy is None:
        return False
    return timedelta(0) <= (teraz or datetime.now(timezone.utc)) - kedy < timedelta(hours=hodin)


FIELDS = f"id,updated_time,participants,messages.limit({HISTORIA}){{id,created_time,from,to,message,attachments}}"


def conversation_page(token: str, account_id: str, after: str = '') -> Dict[str, Any]:
    # Nested message/attachment expansion is expensive (25 chats approached the 20 s timeout).
    params = dict(platform='instagram', fields=FIELDS, limit=5)
    if after:
        params['after'] = after
    result = _volaj(_url(f'{account_id}/conversations', token, **params))
    paging = result.get('paging') or {}
    return {'data': result.get('data') or [],
            'after': str((paging.get('cursors') or {}).get('after') or '') if paging.get('next') else ''}


def conversation(token: str, thread_id: str) -> Dict[str, Any]:
    return _volaj(_url(thread_id, token, fields=FIELDS))


def react(token: str, account_id: str, igsid: str, mid: str) -> Dict[str, Any]:
    return _volaj(_url(f'{account_id}/messages', token), {
        'recipient': {'id': igsid}, 'sender_action': 'react',
        'payload': {'message_id': mid, 'reaction': 'love'}})


def mark_seen(token: str, account_id: str, igsid: str) -> Dict[str, Any]:
    """Explicit receipt, used only immediately before an approved/reserved reply."""
    return _volaj(_url(f'{account_id}/messages', token), {
        'recipient': {'id': igsid}, 'sender_action': 'mark_seen'}, timeout=3.0)


def send_photo(token: str, account_id: str, igsid: str, url: str) -> Dict[str, Any]:
    return _volaj(_url(f'{account_id}/messages', token), {
        'recipient': {'id': igsid}, 'message': {'attachment': {
            'type': 'image', 'payload': {'url': url}}}})


def rozober(konverzacia: Dict[str, Any], moje_id: str) -> Dict[str, Any]:
    """Konverzácia z API → to, s čím vieme pracovať.

    Vracia `igsid` druhej strany, jeho meno a správy zoradené od najstaršej.
    Instagram ich dáva od najnovšej, čo je pre históriu do promptu naopak.
    """
    spravy_raw = ((konverzacia.get("messages") or {}).get("data")) or []
    spravy: List[Dict[str, Any]] = []
    igsid = ""
    username = ""

    for sprava in reversed(spravy_raw):
        odosielatel = sprava.get("from") or {}
        kto = str(odosielatel.get("id") or "")
        je_moja = kto == str(moje_id)
        if not je_moja and kto:
            igsid = igsid or kto
            username = username or str(odosielatel.get("username") or "")
        text = str(sprava.get("message") or "").strip()
        from conversation_policy import input_kind
        kind = input_kind(text, story=bool(sprava.get('reply_to')))
        attachments = (sprava.get('attachments') or {}).get('data') or []
        if not text:
            # Fotka, sticker alebo reakcia — text nemáme, ale je to jeho ťah
            # a musí byť v histórii, inak modelka odpovie do prázdna.
            text = "[poslal médium bez textu]" if not je_moja else "[sent media]"
        spravy.append(
            {
                "mid": str(sprava.get("id") or ""),
                "role": "assistant" if je_moja else "user",
                "content": text,
                "created_time": sprava.get("created_time"),
                "kind": kind,
                "has_image": any(a.get('image_data') or a.get('mime_type', '').startswith('image/') for a in attachments),
                # Ephemeral provider URLs stay in memory; the media worker
                # stores private bytes and stable attachment identifiers only.
                "attachments": attachments,
            }
        )

    if not igsid:
        # Účastníci ako záloha: konverzácia môže mať v posledných dvadsiatich
        # správach len naše vlastné.
        for ucastnik in ((konverzacia.get("participants") or {}).get("data")) or []:
            kto = str(ucastnik.get("id") or "")
            if kto and kto != str(moje_id):
                igsid = kto
                username = username or str(ucastnik.get("username") or "")
                break

    return {
        "id": str(konverzacia.get("id") or ""),
        "igsid": igsid,
        "username": username,
        "updated_time": konverzacia.get("updated_time"),
        "spravy": spravy,
    }
