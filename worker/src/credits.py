"""Meranie a účtovanie LLM volaní.

MeteredLlm má rovnaké verejné metódy ako Llm — moduly predlohy nič nepoznajú.
Pred volaním kontrola zostatku (≤0 → OutOfCredits + pauza modelu), po volaní
zápis do ledgeru: atlas cena z cenníka, klientovi × multiplier.

Neobmedzené účty (`accounts.unlimited`) kontrolu preskakujú — nikdy sa
nepauzujú a nič sa im neodpočíta, ale do ledgeru sa zapisujú rovnako.

ÚČTUJE SA AJ PÁD
----------------
`Llm._chat` opakuje pokus po 429/5xx a poskytovateľ si tokeny z každého pokusu
účtuje. Preto sa `last_usage` v `llm.py` SČÍTAVA cez celé logické volanie a
`_bill` beží aj na chybovej vetve — inak by trojnásobný pokus, ktorý nakoniec
zlyhal, nezaplatil nikto (okrem nás).
"""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)

# `chat` je vyhradený pre správu, ktorú modelka naozaj napísala a odoslala —
# dashboard z počtu týchto riadkov robí dlaždicu „Replies sent". `structured`
# preto NIE JE chat: to sú pomocné volania na pozadí jednej odpovede (sudca,
# pamäťové tvrdenia, fakty, recall, hovorená forma hlasovky), na Simone ich
# vychádza ~0.4 na odpoveď. Kým sa delili o ten istý štítok, klient videl
# násobok toho, čo modelka reálne odoslala.
KIND_BY_METHOD = {"reply": "chat", "structured": "assist", "summarize": "summary",
                  "describe_image": "vision", "transcribe_voice": "audio"}

# Rovnaká jednotka aj slovník ako v appke (`web/lib/credits.ts`) — majiteľ číta
# obe hlášky a nesmie z nich mať pocit, že ide o dva rôzne zostatky.
OUT_OF_CREDITS_MSG = (
    "You are out of Pipe Coins — she has stopped replying. "
    "Top up your balance and she picks up where she left off."
)

# Chýbajúci cenník je konfiguračná chyba, nie udalosť — warning stačí raz za
# proces a slug, inak by log zaplavila každá jedna odpoveď každého tenanta.
_MISSING_PRICE_WARNED: set = set()


class OutOfCredits(RuntimeError):
    pass


class MeteredLlm:
    def __init__(self, llm, registry, model_id: str, model_slug: str,
                 fallback_per_mtok: float = 5.0, notify=None) -> None:
        self._llm = llm
        self._reg = registry
        self._model_id = model_id
        self._slug = model_slug
        self._fallback = fallback_per_mtok
        # Async callable (typicky ControlBot.notify) — správa majiteľovi, že
        # kredit došiel. None = kontrolný bot nebeží, len sa pauzuje.
        self._notify = notify
        self._paused_notified = False

    def __getattr__(self, name):          # metódy Llm, ktoré nemeriame (close…)
        return getattr(self._llm, name)

    async def _metered(self, method: str, *args, **kwargs):
        # Neobmedzený účet (superadmin, interné modelky) sa nekontroluje vôbec:
        # žiadna pauza, žiadna správa majiteľovi. Meranie tým NEKONČÍ — usage
        # sa zapíše nižšie rovnako a `record_usage` len na strane DB preskočí
        # odpočet, takže reálna spotreba ostáva v admin číslach vidieť.
        balance, unlimited = await self._reg.credit_state(self._model_id)
        if not unlimited and balance <= 0:
            # Kým sa runner zastaví (pool ho odpojí do ~30 s), stihne prísť
            # ďalších správ — stav aj správu majiteľovi preto posielame len
            # pri PRVOM zistení, inak by to bol spam do chatu aj do DB.
            if not self._paused_notified:
                self._paused_notified = True
                await self._reg.set_status(self._model_id, "paused", "out_of_credits")
                if self._notify is not None:
                    try:
                        await self._notify(OUT_OF_CREDITS_MSG)
                    except Exception:  # noqa: BLE001 — nedoručená správa nič nemení
                        log.exception("Správa o vyčerpaných kreditoch neodišla")
            raise OutOfCredits(self._model_id)
        try:
            result = await getattr(self._llm, method)(*args, **kwargs)
        except Exception:
            # Volanie padlo, ale tokeny už zhoreli — `Llm._chat` si spotrebu
            # zo VŠETKÝCH pokusov sčítava do `last_usage`, takže tu je čo
            # zaúčtovať. Bez tohto by neúspešné volanie (typicky tri pokusy
            # po 429) platil Atlas z vlastného. Výnimka ide ďalej nezmenená.
            await self._bill(method)
            raise
        await self._bill(method)
        return result

    async def _bill(self, method: str) -> None:
        """Zapíše spotrebu posledného volania do ledgeru. Nikdy nehádže.

        Volá sa aj po páde volania — preto je celé telo best-effort: účtovanie
        nesmie prekryť pôvodnú chybu ani zhodiť úspešnú odpoveď.
        """
        try:
            await self._bill_inner(method)
        except Exception:  # noqa: BLE001 — účtovanie nikdy nezhodí volanie
            log.exception("Zaúčtovanie spotreby zlyhalo")

    async def _bill_inner(self, method: str) -> None:
        usage = getattr(self._llm, "last_usage", None) or {}
        i, o = int(usage.get("input", 0) or 0), int(usage.get("output", 0) or 0)
        if i <= 0 and o <= 0:
            # Volanie nedošlo k modelu (DNS, timeout pred odpoveďou) — zapisovať
            # nulový riadok by len zaplnil ledger bez informácie.
            return
        price = await self._reg.pricing(self._slug)
        if price.get("input_usd_per_mtok") or price.get("output_usd_per_mtok"):
            atlas = i / 1e6 * float(price["input_usd_per_mtok"]) \
                  + o / 1e6 * float(price["output_usd_per_mtok"])
        else:
            if self._slug in _MISSING_PRICE_WARNED:
                log.debug("Chýba cenník pre %s — fallback %.2f/Mtok", self._slug, self._fallback)
            else:
                _MISSING_PRICE_WARNED.add(self._slug)
                log.warning("Chýba cenník pre %s — fallback %.2f/Mtok", self._slug, self._fallback)
            atlas = (i + o) / 1e6 * self._fallback
        charged = atlas * float(price.get("multiplier", 2.0))
        try:
            await self._reg.record_usage(self._model_id, KIND_BY_METHOD[method],
                                         i, o, 0, round(atlas, 6), round(charged, 6))
        except Exception:
            log.exception("Zápis usage zlyhal — odpoveď ide ďalej, dorovná sa ďalším volaním")

    async def charge_unit(self, kind: str, key: str, default_price: float) -> None:
        """Zauctuje jeden kus (hlasovka/fotka) po USPESNOM odoslani.

        Je to tu, a nie v userbote, aby vsetko uctovanie islo cez jedno miesto —
        tokeny aj kusy. Cena sa cita z `app_config` v DB (tu istu hodnotu
        zobrazuje web), nie z konstanty v kode.
        """
        await self._reg.charge_unit(self._model_id, kind, key, default_price)

    async def reply(self, *a, **kw): return await self._metered("reply", *a, **kw)
    # `suggest` sem pribudlo neskôr než ostatné a chvíľu chýbalo — padalo cez
    # `__getattr__` rovno na `Llm`, takže KAŽDÝ návrh v poloautomate, každé
    # pregenerovanie a každá veta z generátora sa modelu zaplatili, ale
    # klientovi sa nezaúčtovali. Meraný musí byť každý spôsob, ako sa dá
    # minúť token.
    async def suggest(self, *a, **kw): return await self._metered("suggest", *a, **kw)
    async def structured(self, *a, **kw): return await self._metered("structured", *a, **kw)
    async def summarize(self, *a, **kw): return await self._metered("summarize", *a, **kw)
    async def describe_image(self, *a, **kw): return await self._metered("describe_image", *a, **kw)
    async def transcribe_voice(self, *a, **kw): return await self._metered("transcribe_voice", *a, **kw)
