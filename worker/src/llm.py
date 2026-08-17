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
        # Token usage z posledného volania — číta MeteredLlm (credits.py) po
        # každom volaní, aby vedel zapísať do ledgeru.
        self.last_usage: Dict[str, int] = {}

    def _capture_usage(self, data: Dict[str, Any]) -> None:
        usage = data.get("usage") or {}
        try:
            self.last_usage = {
                "input": int(usage.get("prompt_tokens", 0) or 0),
                "output": int(usage.get("completion_tokens", 0) or 0),
            }
        except (TypeError, ValueError):
            self.last_usage = {"input": 0, "output": 0}

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

        last_error: Optional[Exception] = None
        for attempt in range(1, _RETRIES + 1):
            try:
                r = await self._client.post(self._endpoint, json=payload)
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"LLM {r.status_code}: {r.text[:200]}", request=r.request, response=r
                    )
                r.raise_for_status()
                data = r.json()
                self._capture_usage(data)
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
        instruction = (
            "Describe this photo factually in at most 12 words. "
            "Then on a new line write exactly EXPLICIT if it shows nudity, genitals "
            "or a sexual act, otherwise write exactly NORMAL."
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
        explicit = any(line.upper() == "EXPLICIT" for line in lines)
        description = " ".join(
            line for line in lines if line.upper() not in ("EXPLICIT", "NORMAL")
        )
        return {"description": description[:160], "explicit": explicit}
