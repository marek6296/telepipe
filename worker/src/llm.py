"""OpenRouter klient — generovanie odpovede a prepis rolling summary."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_RETRIES = 3


class LlmError(RuntimeError):
    pass


def _json_or_empty(response: Any) -> Dict[str, Any]:
    """Telo odpovede ako slovník. Nečitateľné telo = prázdny slovník.

    Chybová odpoveď nemusí byť JSON (HTML z proxy, prázdne telo pri timeoute)
    a pri čítaní spotreby to nesmie vadiť — je to bonus, nie podmienka.
    """
    try:
        data = response.json()
    except Exception:  # noqa: BLE001 - nečitateľné telo nie je chyba volania
        return {}
    return data if isinstance(data, dict) else {}


class Llm:
    """OpenAI-kompatibilný chat klient — funguje pre OpenRouter aj priamo pre xAI."""

    def __init__(
        self,
        api_key: str,
        model: str,
        summary_model: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        reasoning_effort: Optional[str] = "low",
        vision_model: str = "google/gemini-3.5-flash",
        audio_model: str = "google/gemini-3.5-flash",
    ) -> None:
        self._model = model
        self._summary_model = summary_model or model
        # Grok obrázky neberie, preto na videnie fotiek samostatný model.
        self._vision_model = vision_model
        # Zvuk berie Gemini, Grok ani qwen-vl ho neprijmú.
        self._audio_model = audio_model
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        # Grok aj DeepSeek sú reasoning modely a reasoning tokeny sa počítajú
        # do max_tokens. "low" ich zrezalo z ~300 na ~30 → lacnejšie aj rýchlejšie.
        self._reasoning_effort = reasoning_effort or None
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Title": "tg-ai-autoreply",
            },
            timeout=90.0,
        )
        # Token usage z posledného LOGICKÉHO volania — číta MeteredLlm
        # (credits.py) po každom volaní, aby vedel zapísať do ledgeru.
        self.last_usage: Dict[str, int] = {}

    def _reset_usage(self) -> None:
        """Nové logické volanie = nový súčet. Volá sa na začiatku každej
        verejnej metódy, nie pri každom HTTP pokuse."""
        self.last_usage = {"input": 0, "output": 0}

    def _capture_usage(self, data: Dict[str, Any]) -> None:
        """PRIPOČÍTA spotrebu jednej odpovede k súčtu za toto volanie.

        Zámerne sa neprepisuje: `_chat` opakuje pokus po 429/5xx aj po
        prázdnom contente a poskytovateľ si tokeny z neúspešného pokusu
        účtuje rovnako. Prepisovaním by sa fakturovala len posledná odpoveď
        a všetko, čo zhorelo cestou, by šlo na náš účet.
        """
        usage = data.get("usage") or {}
        try:
            pridaj_in = int(usage.get("prompt_tokens", 0) or 0)
            pridaj_out = int(usage.get("completion_tokens", 0) or 0)
        except (TypeError, ValueError):
            return
        self.last_usage = {
            "input": int(self.last_usage.get("input", 0) or 0) + pridaj_in,
            "output": int(self.last_usage.get("output", 0) or 0) + pridaj_out,
        }

    async def close(self) -> None:
        await self._client.aclose()

    async def _chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort

        # Súčet za CELÉ volanie vrátane opakovaní — viď `_capture_usage`.
        self._reset_usage()
        last_error: Optional[Exception] = None
        for attempt in range(1, _RETRIES + 1):
            try:
                r = await self._client.post(self._endpoint, json=payload)
                # Spotreba sa berie ešte PRED kontrolou stavu: aj 429/5xx nesie
                # `usage`, keď model prompt spracoval a odpoveď len nedoručil.
                # Tie tokeny sú minuté a bez tohto by ich nezaplatil nikto.
                self._capture_usage(_json_or_empty(r))
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"LLM {r.status_code}: {r.text[:200]}", request=r.request, response=r
                    )
                r.raise_for_status()
                data = r.json()
                choices = data.get("choices") or []
                if not choices:
                    raise LlmError(f"LLM nevrátil žiadne choices: {str(data)[:300]}")

                choice = choices[0]
                content = (choice.get("message", {}).get("content") or "").strip()
                if content:
                    return content

                # Reasoning model spotreboval celý budget na myslenie a na text
                # nezostalo nič. Zdvihni strop a skús znova.
                if choice.get("finish_reason") == "length" and attempt < _RETRIES:
                    payload["max_tokens"] = int(payload["max_tokens"] * 2)
                    log.warning(
                        "Prázdny content (finish_reason=length), zdvíham max_tokens na %s",
                        payload["max_tokens"],
                    )
                    continue
                raise LlmError(
                    f"LLM vrátil prázdny content (finish_reason="
                    f"{choice.get('finish_reason')})"
                )
            except Exception as exc:  # noqa: BLE001 - retry na čokoľvek prechodné
                last_error = exc
                if attempt == _RETRIES:
                    break
                wait = 2 ** attempt
                log.warning("LLM pokus %s zlyhal (%s), skúšam za %ss", attempt, exc, wait)
                await asyncio.sleep(wait)
        raise LlmError(f"LLM zlyhal po {_RETRIES} pokusoch: {last_error}")

    async def reply(self, system_prompt: str, history: List[Dict[str, str]]) -> str:
        messages = [{"role": "system", "content": system_prompt}] + history
        # Strop musí pokryť reasoning + text; o krátkosť odpovede sa stará prompt.
        return await self._chat(self._model, messages, max_tokens=1200, temperature=0.9)

    async def suggest(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        n: int = 3,
        angles: Optional[List[str]] = None,
        seed: str = "",
    ) -> List[str]:
        """Semi-auto: `n` alternatívnych odpovedí v jej hlase, prvá je najlepšia
        (tú pošle časový fallback).

        PREČO `angles`. Pôvodne sa pýtalo na „iný uhol/nálada (hravá, vrúcna,
        dráždivá)" a výsledkom boli tri takmer identické správy — naostro
        prišli tri verzie vety „hey, just chillin in bed". Nálada nie je ťah:
        keď model dostane rovnaké zadanie trikrát, napíše ho trikrát rovnako,
        len s iným emoji. `angles` sú preto TŘI RÔZNE ŤAHY v konverzácii (choď
        s ním ďalej / natiahni to k obsahu / nechaj hovoriť jeho) a volajúci
        ich volí podľa kanála: na Fanvue sa predáva, na Telegrame nie.

        Všetky tri musia sedieť na to isté, čo prišlo — sú to alternatívy tej
        istej chvíle, nie tri nezávislé nápady.

        `seed` mení zadanie pri pregenerovaní. Bez neho by model na rovnaký
        vstup vrátil to isté a tlačidlo „Regenerate" by nerobilo nič.
        """
        marker = "~~~"
        uhly = angles or [
            "nadviaž priamo na to, čo napísal",
            "posuň to o krok ďalej, smelšie",
            "vráť loptičku jemu — nech povie viac",
        ]
        rozpis = "\n".join(f"{i + 1}. {u}" for i, u in enumerate(uhly[:n]))
        instruction = (
            f"\n\n[REŽIM NÁVRHOV] Napíš PRESNE {n} verzie svojej ďalšej odpovede. "
            f"Každá je INÝ ŤAH v tejto konverzácii:\n{rozpis}\n"
            "Pravidlá, ktoré platia pre všetky tri:\n"
            "— všetky reagujú na TO ISTÉ, čo práve napísal, a na to, o čom ste sa "
            "bavili; žiadny variant nesmie byť veta, ktorá by sedela do "
            "hocijakého chatu\n"
            "— aspoň jedna z nich sa oprie o niečo konkrétne z posledných správ\n"
            "— pokyny vyššie (kde si, čo práve robíš, čo máš robiť s obsahom) "
            "platia pre všetky tri rovnako; líšia sa ťahom, nie tým, či ich "
            "poslúchnu\n"
            "— nesmú byť tri verzie tej istej vety s inými emoji\n"
            f"Zoraď ich od NAJLEPŠEJ po najslabšiu. Oddeľ riadkom, ktorý obsahuje "
            f"len „{marker}“. Žiadne číslovanie, nadpisy ani vysvetlenia."
        )
        if seed:
            instruction += (
                f"\n[NOVÝ POKUS {seed}] Predchádzajúce návrhy sa nepáčili. "
                "Napíš iné — iné otvorenie, iná dĺžka, iný spôsob, ako to uchopiť. "
                "Nezopakuj tie isté vety."
            )
        messages = [{"role": "system", "content": system_prompt + instruction}] + history
        raw = await self._chat(self._model, messages, max_tokens=1400, temperature=0.95)
        parts = [p.strip() for p in raw.split(marker)]
        out = [p for p in parts if p]
        if not out:  # model marker nepoužil — ber celú odpoveď ako jediný návrh
            out = [raw.strip()] if raw.strip() else []
        return out[:n]

    async def structured(
        self,
        system_prompt: str,
        content: str,
        max_tokens: int = 900,
        temperature: float = 0.1,
    ) -> str:
        """Rozhodovanie a extrakcia — nie písanie.

        Odpoveď modelky sa generuje pri 0.9, lebo tam je nápaditosť žiaduca.
        Extraktor faktov ani sudca ju nechcú: pri vysokej teplote raz vráti
        kľúč „work“, inokedy „job“, a `merge_plan` potom namiesto potvrdenia
        faktu založí nový. Sudca zas ten istý návrh raz prepustí a inokedy
        prepíše. Tu je cieľom zopakovateľnosť, takže teplota ide dole.
        """
        return await self._chat(
            self._model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def summarize(self, fact_sheet: str, transcript: str) -> str:
        """Zhrnutie DYNAMIKY — nie faktov. Tie majú vlastnú tabuľku.

        Fakty aj epizódy idú do promptu samostatne, takže keby zhrnutie
        prerozprávalo to isté, mal by model tú istú informáciu trikrát a
        v prompte by ubral priestor tomu, čo nikde inde nie je: ako sa ten
        rozhovor vlastne vyvíja a čo v ňom funguje.

        Fakty sa posielajú len ako podklad — aby zhrnutie neopakovalo to,
        čo už z nich model vidí.
        """
        system = (
            "Si asistentka, ktorá si vedie poznámky o TÓNE konverzácie, nie o faktoch.\n"
            "Fakty o ňom už máme zvlášť — tie NEOPAKUJ.\n\n"
            "Napíš maximálne 6 krátkych bodov o tom:\n"
            "- na aký tón a témy reagoval dobre a kedy naopak stíchol\n"
            "- ako sa medzi nimi vyvíja nálada a koľko si dovolí\n"
            "- čo mu už bolo sľúbené alebo naznačené\n"
            "- ako píše a ako rýchlo odpovedá\n"
            "- čo mu povedala HLASOM (je to pri tých správach uvedené) — po "
            "týždni sa inak nedá zistiť, či mu niečo povedala alebo napísala, "
            "a to je rozdiel, ktorý si človek pamätá\n\n"
            "Bez úvodných fráz, maximálne 120 slov. Nič si nedomýšľaj."
        )
        user = (
            f"Fakty, ktoré už máme (len ako kontext, neprepisuj ich):\n"
            f"{fact_sheet or '(zatiaľ žiadne)'}\n\n"
            f"Priebeh konverzácie:\n{transcript}\n\n"
            f"Napíš poznámky o tóne."
        )
        return await self._chat(
            self._summary_model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=1200,
            temperature=0.3,
        )


    async def report(self, system: str, podklad: str) -> str:
        """Denný súhrn konverzácií pre majiteľa.

        Ide cez `_summary_model` (lacnejší) zámerne: report nikto nečíta ako
        prózu, chce z neho mená a jednu vetu ku každému. Je to jedno volanie
        denne na modelku, ale zbytočne drahé volanie denne je stále zbytočné.

        Nízka teplota z rovnakého dôvodu ako pri `summarize` — od súhrnu sa
        čaká presnosť, nie nápaditosť.
        """
        return await self._chat(
            self._summary_model,
            [{"role": "system", "content": system}, {"role": "user", "content": podklad}],
            max_tokens=900,
            temperature=0.3,
        )

    async def transcribe_voice(self, data: bytes, fmt: str = "ogg") -> str:
        """Prepíše hlasovku, ktorú poslal klient. Prázdny reťazec = nepodarilo sa.

        Beží na audio modeli — hlavný model zvuk neprijíma. Zlyhanie nesmie
        zablokovať odpoveď, preto sa v takom prípade vráti prázdny prepis.
        """
        import base64

        payload = {
            "model": self._audio_model,
            "max_tokens": 1500,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Prepíš presne, čo je v tejto nahrávke povedané. "
                                "Vráť IBA tie slová, v pôvodnom jazyku, bez úvodu "
                                "a bez úvodzoviek. Ak nie je rozumieť, vráť prázdno."
                            ),
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64.b64encode(data).decode(),
                                "format": fmt,
                            },
                        },
                    ],
                }
            ],
        }
        self._reset_usage()
        try:
            r = await self._client.post(self._endpoint, json=payload)
            r.raise_for_status()
            data_resp = r.json()
            self._capture_usage(data_resp)
            content = (data_resp["choices"][0]["message"].get("content") or "").strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("Hlasovku sa nepodarilo prepísať: %s", exc)
            return ""
        return content.strip().strip('"')[:600]

    async def describe_image(self, data: bytes, mime: str = "image/jpeg") -> Dict[str, Any]:
        """Popíše prijatú fotku a povie, či je explicitná.

        Beží na samostatnom vision modeli — hlavný model obrázky neprijíma.
        Pri zlyhaní vráti prázdny popis, aby to nezablokovalo odpoveď.
        """
        import base64

        encoded = base64.b64encode(data).decode()
        # DRUH OBRÁZKA JE ROVNAKO DÔLEŽITÝ AKO POPIS. Bez neho vyzerá screenshot
        # v histórii ako obyčajná fotka: naostro poslal snímku JEJ instagramovej
        # story a modelka mu napísala „damn u look good in that suit 😘" —
        # pochválila ho za muža z jej vlastnej story. Odpovedal „which suit,
        # that's your story 😄" a konverzácia sa už nespamätala.
        instruction = (
            "Line 1: describe this image factually in at most 12 words.\n"
            "Line 2: exactly one word — SCREENSHOT if it is a screen capture "
            "(phone status bar, app or website interface, chat, profile, story), "
            "PERSON if it is a photo of a person, OTHER for anything else.\n"
            "Line 3: exactly EXPLICIT if it shows nudity, genitals or a sexual "
            "act, otherwise exactly NORMAL."
        )
        payload = {
            "model": self._vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "max_tokens": 300,
        }
        self._reset_usage()
        try:
            r = await self._client.post(self._endpoint, json=payload)
            r.raise_for_status()
            data_resp = r.json()
            self._capture_usage(data_resp)
            content = (data_resp["choices"][0]["message"].get("content") or "").strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("Fotku sa nepodarilo popísať: %s", exc)
            return {"description": "", "explicit": False}

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        znacky = {"EXPLICIT", "NORMAL", "SCREENSHOT", "PERSON", "OTHER"}
        explicit = any(line.upper() == "EXPLICIT" for line in lines)
        druh = next(
            (line.upper() for line in lines if line.upper() in ("SCREENSHOT", "PERSON")),
            "",
        )
        description = " ".join(line for line in lines if line.upper() not in znacky)
        return {
            "description": description[:160],
            "explicit": explicit,
            "kind": druh,
        }
