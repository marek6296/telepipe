"""Čo má control bot modelky hlásiť majiteľovi.

PREČO SAMOSTATNÝ MODUL
----------------------
Rozhodnutie „toto sa hlási, toto nie" sa dotýka troch miest: Fanvue udalostí,
kreditu a denného reportu. Kým to bolo rozsypané, nedalo sa otestovať a nedalo
sa na jednom mieste pozrieť, čo klientovi vlastne chodí.

FORMÁTOVANIE JE MARKDOWN, NIE HTML
----------------------------------
Control bot posiela cez Telethon, ktorý používa markdown (`*tučné*`). Náš shop
bot (`web/lib/telegram-shop.ts`) ide cez Bot API s `parse_mode: HTML`, takže
tam sa píše `<b>`. Sú to dve rôzne cesty a zámena je vidieť okamžite: v chate
sa zobrazia holé značky namiesto tučného textu.

TEXTY SÚ ZÁMERNE KRÁTKE
-----------------------
Control bot je ovládač, nie čítanka. Notifikácia má povedať ČO sa stalo a
s KÝM, nič viac — kto chce detail, otvorí Fanvue. Dlhá správa v telefóne o
druhej ráno nikomu nepomôže.

NEZNÁME UDALOSTI SA LOGUJÚ, NIE IGNORUJÚ
----------------------------------------
Fanvue posiela typy, ktoré sme nikdy nevideli (`follow` je otázny — za týždeň
prevádzky prišli len lajky, komentáre a správy). Namiesto tichého zahodenia sa
neznámy typ zaloguje, aby sme sa dozvedeli, čo vlastne existuje.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

# Typ udalosti -> (stĺpec v `control_bot_settings`, ikona, popis)
#
# Kľúče sú v oboch tvaroch, aké Fanvue používa — s prefixom `creator.` aj bez.
# `follow` je tu v troch variantoch zámerne: nevieme, ktorý (ak vôbec) posiela,
# a hádať jeden by znamenalo, že notifikácia ticho nikdy nepríde.
UDALOSTI: Dict[str, Tuple[str, str, str]] = {
    "creator.subscription.activated": ("notify_fanvue_subscribe", "⭐", "New subscriber"),
    "subscription.activated":         ("notify_fanvue_subscribe", "⭐", "New subscriber"),
    "creator.payment.succeeded":      ("notify_fanvue_payment", "💰", "Payment received"),
    "payment.succeeded":              ("notify_fanvue_payment", "💰", "Payment received"),
    "creator.follow.created":         ("notify_fanvue_follow", "👀", "New follower"),
    "creator.follower.added":         ("notify_fanvue_follow", "👀", "New follower"),
    "follow.created":                 ("notify_fanvue_follow", "👀", "New follower"),
    "creator.post.liked":             ("notify_fanvue_like", "❤️", "Post liked"),
    "creator.post.commented":         ("notify_fanvue_comment", "💬", "New comment"),
}

# Typy, o ktorých vieme a hlásiť sa nemajú — nech nezaplavia log ako „neznáme".
TICHE = frozenset({
    "creator.message.received",
    "creator.message.sent",
    "creator.message.read",
})

_videne_nezname: set[str] = set()

# Pod týmto zostatkom sa hlási. Zhruba 50 odpovedí — dosť na to, aby stihol
# dobiť skôr, než modelka stíchne, a málo na to, aby to otravovalo.
PRAH_COINOV = 3000


def _povolene(nastavenia: Optional[Dict[str, Any]], stlpec: str, default: bool) -> bool:
    """Chýbajúci riadok = defaulty, nie ticho.

    Modelka založená pred touto migráciou nemá riadok a bolo by horšie
    nehlásiť jej nič, než hlásiť podľa rozumného základu.
    """
    if not nastavenia:
        return default
    hodnota = nastavenia.get(stlpec)
    return default if hodnota is None else bool(hodnota)


def sprava_k_udalosti(
    event: Dict[str, Any],
    nastavenia: Optional[Dict[str, Any]],
    meno_fana: str = "",
    suma: str = "",
) -> Optional[str]:
    """Text do control bota, alebo `None` keď sa hlásiť nemá."""
    typ = str(event.get("event_type") or event.get("type") or "").strip()
    if not typ or typ in TICHE:
        return None

    zaznam = UDALOSTI.get(typ)
    if zaznam is None:
        # Raz za beh na typ — inak by pri každom lajku pribudol riadok.
        if typ not in _videne_nezname:
            _videne_nezname.add(typ)
            log.info("Fanvue: neznámy typ udalosti %r — zatiaľ sa nehlási", typ)
        return None

    stlpec, ikona, popis = zaznam
    # Odber a platba sú defaultne zapnuté (sú to peniaze), zvyšok vypnutý.
    default = stlpec in ("notify_fanvue_subscribe", "notify_fanvue_payment")
    if not _povolene(nastavenia, stlpec, default):
        return None

    riadky = [f"{ikona} *{popis}*"]
    kto = (meno_fana or "").strip()
    if kto:
        riadky.append(kto)
    if suma:
        riadky.append(suma)
    return " · ".join(riadky)


def sprava_o_kredite(coins: float, nastavenia: Optional[Dict[str, Any]]) -> Optional[str]:
    """Dochádzajúce Pipe Coiny.

    Prah je v `limity`, nie tu — toto len skladá text. Zámerne hovorí aj to,
    čo sa stane, keď dôjdu: bez toho je to len číslo bez následku.
    """
    if not _povolene(nastavenia, "notify_credits_low", True):
        return None
    return (
        f"🪙 *Pipe Coins are running low*\n"
        f"About {int(coins):,} left.\n"
        "When they run out she stops replying. Top up in the dashboard or "
        "right here with /menu → Top up."
    ).replace(",", " ")
