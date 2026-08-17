"""ElevenLabs — jej hlas a miestnosť za ňou.

Dva volania a nič viac: text sa prehovorí jej hlasom a k tomu sa vyrobí
niekoľkosekundový zvuk miestnosti. Zmiešanie a telefónny zvuk robí `livevoice`
cez ffmpeg, lebo tam sú na to už nástroje.

Účty sú oddelené — kľúč aj hlas sedia v `behavior` každej modelky zvlášť,
takže kamošov účet používa svoj vlastný kľúč a svoj vlastný hlas.

Všetko je fail-open: keď sa nahrávka nepodarí, vráti sa None a odpoveď odíde
ako text. Hlas je bonus, nie podmienka.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import httpx

log = logging.getLogger(__name__)

BASE = "https://api.elevenlabs.io/v1"
TIMEOUT_S = 90.0

# v3 rozumie smerovaniu hrania v hranatých zátvorkách a znie oveľa živšie.
MODEL_ID = "eleven_v3"
FALLBACK_MODEL_ID = "eleven_multilingual_v2"

# Miestnosti pre pozadie.
#
# Prompty sú zámerne konkrétne zvuky, nie „room tone". Keď sa model požiada
# o samotné ticho miestnosti, vráti široký šum, ktorý pod hlasom znie ako
# sykot — a presne to bol prvý pokus. Keď dostane udalosti (auto za oknom,
# televízor vo vedľajšej izbe), vyrobí zvuk so štruktúrou, ktorý sa dá stíšiť
# a ostane z neho dojem miesta.
AMBIENCES: Dict[str, str] = {
    "home": "single car passing outside a closed window, distant muffled city, calm",
    "bedroom": "faint television murmuring in another room at night, very distant, calm",
    "kitchen": "fridge compressor humming quietly, a spoon set down on a counter once",
    "bathroom": "single water drop into a sink, small tiled room, quiet",
    "car": "car engine idling steadily, muffled road under tyres",
    "outside": "footsteps on pavement, a car passing, light wind in trees",
    "cafe": "muffled distant conversation, a cup on a saucer, espresso machine far away",
    # Fitko padne v rozhovoroch najčastejšie zo všetkých miest, takže má vlastnú
    # miestnosť — „outside" pod ním znelo ako ulica a nesedelo to.
    "gym": "distant weight plates clinking once, muffled gym music, room echo",
    "none": "",
}


async def list_voices(api_key: str) -> list:
    """Hlasy na tom účte — aby sa voice_id neopisovalo ručne.

    Vracia [{"id", "name", "preview"}]. Prázdny zoznam = kľúč nesedí alebo
    služba nebeží; volajúci to má ukázať ako chybu, nie ako „žiadne hlasy".
    """
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{BASE}/voices", headers={"xi-api-key": api_key})
            r.raise_for_status()
            rows = (r.json() or {}).get("voices") or []
    except Exception as exc:  # noqa: BLE001 - dashboard ukáže prázdny zoznam
        log.warning("Zoznam hlasov sa nepodarilo načítať: %s", exc)
        return []
    return [
        {
            "id": v.get("voice_id") or "",
            "name": v.get("name") or "(bez mena)",
            "preview": v.get("preview_url") or "",
        }
        for v in rows
        if v.get("voice_id")
    ]


# Ktoré modely `speed` naozaj poslúchnu.
#
# Odmerané na tej istej vete: v3 bez speed 8,32 s, so speed 1.15 dokonca
# 10,48 s — čísla nedávajú zmysel, je to len rozptyl medzi nahrávkami. v2
# na tom istom mieste: 9,06 s bez, 6,04 s so speed 1.15. Preto sa pri v3
# musí tempo dorobiť pri mixe, kým to ElevenLabs nedoplní.
HONOURS_SPEED = frozenset({FALLBACK_MODEL_ID})


async def speech(
    text: str, api_key: str, voice_id: str, speed: Optional[float] = None
) -> tuple:
    """Prehovorí text jej hlasom.

    Vracia (zvuk, model). Model je dôležitý pre volajúceho: keď ho `speed`
    poslúchol, netreba nahrávku doháňať cez atempo, ktoré hlas znehodnocuje.
    (None, "") = nepodarilo sa.
    """
    if not (text and api_key and voice_id):
        return None, ""
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        for model in (MODEL_ID, FALLBACK_MODEL_ID):
            # Nižšia stabilita = živší prednes, vyšší štýl = viac hrania.
            # Stabilný hlas znie ako čítanie a to je presne to, čo chceme
            # z hlasovky dostať preč. Rytmus síce robí hlavne text, ale
            # vyrovnaný prednes ho dokáže zahladiť späť do monotónnosti.
            nastavenia = {"stability": 0.22, "similarity_boost": 0.75, "style": 0.6}
            if speed and model in HONOURS_SPEED:
                # Rozsah, ktorý ElevenLabs berie. Mimo neho vráti 422.
                nastavenia["speed"] = round(max(0.7, min(1.2, float(speed))), 2)
            payload = {"text": text, "model_id": model, "voice_settings": nastavenia}
            try:
                r = await client.post(
                    f"{BASE}/text-to-speech/{voice_id}",
                    json=payload,
                    headers={"xi-api-key": api_key, "accept": "audio/mpeg"},
                )
                if r.status_code == 200 and r.content:
                    return r.content, model
                log.warning("Reč (%s) neprešla: %s %s", model, r.status_code, r.text[:160])
            except Exception as exc:  # noqa: BLE001 - odpoveď odíde ako text
                log.warning("Reč sa nepodarila (%s): %s", model, exc)
    return None, ""


async def ambience(name: str, api_key: str, seconds: float = 12.0) -> Optional[bytes]:
    """Vyrobí zvuk miestnosti. None = bez pozadia, hlas pôjde sám."""
    prompt = AMBIENCES.get(name or "home", AMBIENCES["home"])
    if not (prompt and api_key):
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"{BASE}/sound-generation",
                json={
                    "text": prompt,
                    "duration_seconds": max(4.0, min(22.0, seconds)),
                    # Miestnosť má byť pozadie, nie výjav — nech model nepridáva
                    # udalosti, ktoré by v tichu za rečou vytŕčali.
                    "prompt_influence": 0.25,
                },
                headers={"xi-api-key": api_key, "accept": "audio/mpeg"},
            )
            if r.status_code == 200 and r.content:
                return r.content
            log.warning("Pozadie neprešlo: %s %s", r.status_code, r.text[:160])
    except Exception as exc:  # noqa: BLE001 - bez pozadia sa dá žiť
        log.warning("Pozadie sa nepodarilo: %s", exc)
    return None
