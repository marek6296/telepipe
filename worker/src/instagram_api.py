"""Instagram Graph API — čítanie konverzácií a odosielanie správ.

POLLOVANIE, NIE WEBHOOKY
------------------------
Webhooky Instagramu vyžadujú Advanced Access AJ overenie firmy (dokumentácia
„Setup Webhooks Subscriptions"), takže na vlastnom účte sa zapnúť nedajú.
Conversations API si vystačí so Standard Access. Agent preto konverzácie ťahá
sám — je to pomalšie o dĺžku kola, ale funguje to hneď a bez review.

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

GRAPH = "https://graph.instagram.com"
VERZIA = "v23.0"

# Strop dĺžky správy podľa dokumentácie. V BAJTOCH.
MAX_BAJTOV = 1000

# Okno na odpoveď od jeho poslednej správy.
OKNO_H = 24

# Koľko posledných správ z konverzácie má zmysel pýtať — Instagram detail
# starších než dvadsať aj tak nevráti.
HISTORIA = 20


class InstagramError(RuntimeError):
    """Čokoľvek, čo Instagram odmietol. Nesie aj kód, nech sa dá rozhodnúť."""

    def __init__(self, sprava: str, kod: int = 0, podtyp: str = "") -> None:
        super().__init__(sprava)
        self.kod = kod
        self.podtyp = podtyp


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
        ) from exc
    except Exception as exc:  # noqa: BLE001 - sieť
        raise InstagramError(str(exc)[:300]) from exc


def _url(cesta: str, token: str, **params: Any) -> str:
    params["access_token"] = token
    return f"{GRAPH}/{VERZIA}/{cesta.lstrip('/')}?{urllib.parse.urlencode(params)}"


def profil(token: str) -> Dict[str, Any]:
    """Kto sme. Slúži aj ako kontrola, či token ešte žije."""
    return _volaj(_url("me", token, fields="id,username,account_type"))


def konverzacie(token: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Konverzácie aj so správami, zoradené od najnovšie aktívnej.

    Správy sa ťahajú rovno v jednom dotaze (`messages{...}`) — inak by to bolo
    jedno volanie na konverzáciu a ešte jedno na každú správu.
    """
    out = _volaj(
        _url(
            "me/conversations",
            token,
            platform="instagram",
            fields=f"id,updated_time,participants,messages.limit({HISTORIA})"
                   "{id,created_time,from,to,message}",
            limit=limit,
        )
    )
    return list(out.get("data") or [])


def posli_text(token: str, igsid: str, text: str) -> Dict[str, Any]:
    """Pošle text. Vracia odpoveď Instagramu (obsahuje `message_id`)."""
    orezany = orez(text)
    if not orezany:
        raise InstagramError("prázdna správa")
    return _volaj(
        _url("me/messages", token),
        {"recipient": {"id": str(igsid)}, "message": {"text": orezany}},
    )


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
    return (teraz or datetime.now(timezone.utc)) - kedy < timedelta(hours=hodin)


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
        if not text:
            # Fotka, sticker alebo reakcia — text nemáme, ale je to jeho ťah
            # a musí byť v histórii, inak modelka odpovie do prázdna.
            text = "[poslal médium bez textu]" if not je_moja else ""
            if not text:
                continue
        spravy.append(
            {
                "mid": str(sprava.get("id") or ""),
                "role": "assistant" if je_moja else "user",
                "content": text,
                "created_time": sprava.get("created_time"),
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
