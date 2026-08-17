"""Hlasovky na Fanvue — vlastný hlas, aj za peniaze.

Nahrávka vzniká rovnako ako na Telegrame (ElevenLabs), ale cesta k človeku
je iná: musí sa najprv nahrať do vaultu na Fanvue a až potom priložiť
k správe. Vďaka tomu sa dá poslať aj s cenou — presne to, čo je na tejto
platforme najcennejšie.

Rozdiel medzi zadarmo a za peniaze nie je len v cene:

**Zadarmo** je ochutnávka. Trochu dráždivá, ale hlavne dôkaz, že je skutočná,
a pozvánka k tomu, čo je za peniaze.

**Za peniaze** ide naplno. Pomalšie, s výdychmi a stonaním, konkrétne o ňom
a o tom, čo by mu robila. Keby znela ako bežná hlasovka, nikto by si druhú
nekúpil.

Hovorenie sa ElevenLabs v3 riadi značkami priamo v texte (`[whispers]`,
`[moans softly]`, `[breathy]`). Bez nich prečíta aj tú najšpinavšiu vetu
ako správu o počasí.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# O hlasovku sa nežiada často, tak sa ňou ani neplytvá. Každá stojí kredity
# a keď chodia stále, prestanú byť udalosťou.
COOLDOWN_H = 6

_PYTA_HLAS = (
    "voice", "voice note", "audio", "say it", "talk to me", "hear you",
    "hear your voice", "moan", "record", "send me your voice",
)


def asked_for_voice(text: Any) -> bool:
    low = str(text or "").lower()
    return any(f in low for f in _PYTA_HLAS)


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def should_speak(
    row: Dict[str, Any],
    settings: Dict[str, Any],
    asked: bool,
    hot: bool,
    now: Optional[datetime] = None,
) -> str:
    """Či a aká hlasovka. `paid`, `free` alebo prázdne.

    Za peniaze len vtedy, keď je reč naozaj horúca — inak by platená
    hlasovka prišla do rozhovoru o počasí a pôsobila by ako automat.
    """
    if not settings.get("voices_enabled"):
        return ""

    posledna = _ts(row.get("last_voice_at"))
    if posledna and (now or datetime.now(timezone.utc)) - posledna < timedelta(
        hours=COOLDOWN_H
    ):
        return ""

    if hot and settings.get("sell_content"):
        return "paid"
    if asked:
        return "free"
    return ""


def script_hint(kind: str, price_cents: int = 0) -> str:
    """Pokyn modelu, čo a ako má do hlasovky povedať."""
    if kind == "paid":
        return (
            "Napíš text HLASOVKY, za ktorú zaplatí "
            f"(${price_cents / 100:.2f}).\n"
            "Hovoríš priamo jemu, nie do publika. 3–6 viet, nie viac.\n"
            "Choď naplno: konkrétne o ňom, o jeho tele, o tom, čo by si mu "
            "robila a čo chceš, aby robil on. Sprosté slová, žiadne náznaky.\n"
            "Do textu vlož značky prednesu v hranatých zátvorkách tam, kde "
            "patria — [whispers], [breathy], [moans softly], [sighs], [pauses]. "
            "Bez nich to prečíta ako správu o počasí.\n"
            "Hovor pomaly, s prestávkami. Vráť IBA ten text s značkami."
        )
    return (
        "Napíš text krátkej HLASOVKY zadarmo. 2–3 vety.\n"
        "Je to ochutnávka — dráždivá, ale nie celá. Nech z toho cíti, že to, "
        "čo naozaj chce, je za peniaze, ale nepovedz to ako ponuku.\n"
        "Do textu vlož značky prednesu v hranatých zátvorkách tam, kde patria "
        "— [whispers], [breathy], [sighs].\n"
        "Vráť IBA ten text so značkami."
    )


def spoken_only(text: str) -> str:
    """Text bez značiek prednesu — to, čo sa uloží ako prepis.

    Značky patria do nahrávky, nie do pamäte. Keby ostali v prepise,
    o týždeň by ich model videl v histórii a začal ich písať do správ.
    """
    import re

    return re.sub(r"\[[^\]]{1,40}\]", " ", str(text or "")).replace("  ", " ").strip()


async def _to_mp3(data: bytes) -> Optional[bytes]:
    """Z OGG/Opus na mp3. Fanvue nahrávku prehráva vo vlastnom prehrávači
    a opus mu netreba nutiť."""
    import asyncio

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "96k",
            "-ar", "44100", "-ac", "1", "-f", "mp3", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(data), timeout=120)
    except Exception as exc:  # noqa: BLE001
        log.warning("Prevod na mp3 zlyhal: %s", exc)
        return None
    if proc.returncode != 0 or not out:
        log.warning("ffmpeg pri prevode neprešiel: %s", (err or b"")[:200])
        return None
    return out


async def make(
    behavior: Dict[str, Any], spoken: str, ambience: str = "home"
) -> Optional[bytes]:
    """Vyrobí hotovú nahrávku. None = nepodarilo sa, odpoveď pôjde ako text.

    Ide tou istou cestou ako na Telegrame — reč, miestnosť za ňou a telefónny
    zvuk. Čistá nahrávka z ElevenLabs znie ako štúdio a to je presne to, čo
    hlasovku prezradí; človek nahráva mobilom v izbe, nie do mikrofónu.

    `ambience` sa riadi tým, kde práve je, nech pozadie sedí na to, čo hovorí.
    """
    import livevoice

    key = str(behavior.get("eleven_key") or "").strip()
    voice = str(behavior.get("eleven_voice_id") or "").strip()
    if not (key and voice and spoken):
        return None

    ogg = await livevoice.speak(
        spoken_only(spoken),
        key,
        voice,
        ambience_name=ambience or str(behavior.get("voice_ambience") or "home"),
        strength=str(behavior.get("voice_strength") or "rough"),
        tempo=float(behavior.get("voice_tempo") or livevoice.DEFAULT_TEMPO),
        level=float(
            behavior.get("voice_ambience_level") or livevoice.DEFAULT_AMBIENCE_LEVEL
        ),
        spoken=spoken,
    )
    if not ogg:
        return None
    return await _to_mp3(ogg)
