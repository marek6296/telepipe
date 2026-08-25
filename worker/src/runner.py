"""TenantRunner — jeden tenant (modelka) v spoločnom event loope.

V predlohe (`/Users/marek/telegram/src/main.py:run`) bol jeden proces = jeden
model: config z env, klienti, handlery, `run_until_disconnected()`. V Telepipe
beží desiatky modeliek jeden worker, takže to isté wiring-om zabalíme do triedy,
ktorú pool (Task 11) spustí ako `asyncio.Task` per tenant.

Čo pribudlo oproti predlohe:
  * retry s backoffom — pád jednej modelky nesmie zhodiť ostatné,
  * Fanvue agent vedľa Telegramu (`fanvue_tenant.start_fanvue`) — v predlohe to
    bola samostatná služba (`main_fanvue.py`), tu je to ďalšia úloha tenanta,
    zámerne best-effort: Fanvue nesmie zhodiť odpisovanie na Telegrame,
  * `stop()` na čisté ukončenie (SIGTERM / odobratý lease),
  * mapovanie pádov na stav v `models`: neplatná session → `session_revoked`,
    5× pád po sebe → `crashed_repeatedly`, došli kredity → len pustený lease
    (stav `paused` už nastavila `MeteredLlm`, runner ho neprepisuje).

Importy `userbot`/`control_bot` sú vnútri `_run_once` zámerne: konštruktor aj
`run()` musia byť použiteľné bez nich (testy si `_run_once` podvrhnú).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging

from telethon import TelegramClient
from telethon.errors import AuthKeyUnregisteredError
from telethon.sessions import StringSession

log = logging.getLogger("runner")

# Backoff medzi pokusmi. Piaty pokus už nečaká — vtedy sa model odstavuje.
BACKOFF_S = [30, 60, 300, 900]
MAX_TRIES = 5


class TenantRunner:
    """Beh jednej modelky: klienti, handlery, sweeper, catch-up, dozor."""

    def __init__(self, tenant_cfg, global_cfg, registry, transport) -> None:
        # Závislosti sa smú odovzdať aj ako None — všetko ťažké sa stavia až
        # v `_run_once`, aby sa dal životný cyklus testovať bez Telegramu.
        self._cfg = tenant_cfg
        self._g = global_cfg
        self._reg = registry
        self._transport = transport
        self._stopping = asyncio.Event()
        self._once_task: asyncio.Task | None = None
        # Control bot aktuálneho behu — nastaví ho `_run_once`, používa ho
        # `_ohlas_pad`. `None` = ešte nebeží alebo modelka bota nemá.
        self._control = None
        # Čo treba po sebe upratať — asyncio úlohy a Telethon klienti.
        self._cleanup: list = []

    @property
    def model_id(self) -> str:
        return getattr(self._cfg, "model_id", "?")

    # ---------- životný cyklus ----------

    @staticmethod
    async def _sleep(seconds: float) -> None:
        # Samostatná metóda, nech testy nemusia čakať reálne minúty.
        await asyncio.sleep(seconds)

    async def run(self) -> None:
        """Drží modelku hore, kým to má zmysel. Nikdy nehádže (okrem zrušenia)."""
        tries = 0
        while tries < MAX_TRIES and not self._stopping.is_set():
            tries += 1
            try:
                await self._guarded_once()
                return  # skončilo čisto (disconnect alebo stop)
            except asyncio.CancelledError:
                if self._stopping.is_set():
                    return  # riadené ukončenie, nie chyba
                raise
            except AuthKeyUnregisteredError:
                # Odhlásená session sa opakovaním nespraví platnou — nový login
                # musí spraviť majiteľ (`scripts/login.py`).
                log.error("model %s: session odvolaná — treba nový login", self.model_id)
                await self._park("session_revoked")
                return
            except Exception as exc:  # noqa: BLE001 — pád jednej modelky nezhodí worker
                from credits import OutOfCredits

                if isinstance(exc, OutOfCredits):
                    # `MeteredLlm` už nastavila stav `paused`; runner len pustí
                    # lease, nech ho pool nedrží zbytočne.
                    log.info("model %s: došli kredity — končím", self.model_id)
                    await self._release()
                    return
                log.exception("model %s: pád (pokus %d/%d)", self.model_id, tries, MAX_TRIES)
                if tries < MAX_TRIES and not self._stopping.is_set():
                    await self._sleep(BACKOFF_S[min(tries - 1, len(BACKOFF_S) - 1)])

        if tries >= MAX_TRIES and not self._stopping.is_set():
            log.error("model %s: %d pádov po sebe — odstavujem", self.model_id, MAX_TRIES)
            await self._park("crashed_repeatedly")

    async def stop(self) -> None:
        """Požiada beh o koniec a počká, kým sa upratovanie dokončí."""
        self._stopping.set()
        task, self._once_task = self._once_task, None
        if task is not None and not task.done():
            # `_run_once` má vlastný `finally` — zrušenie ho spustí, takže
            # klienti sa odpoja aj vtedy, keď beh visí na sieti.
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                try:
                    await task
                except Exception:  # noqa: BLE001 — pri stopovaní už je jedno prečo
                    log.exception("model %s: chyba pri ukončovaní", self.model_id)
        await self._drain_cleanup()

    async def _guarded_once(self) -> None:
        """Spustí `_run_once` ako úlohu, nech ju vie `stop()` zrušiť."""
        task = asyncio.create_task(self._run_once())
        self._once_task = task
        try:
            await task
        except asyncio.CancelledError:
            # Zrušili nás zvonku (nie cez `stop()`) — beh nesmie ostať bežať.
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            raise
        finally:
            if self._once_task is task:
                self._once_task = None

    # ---------- pomocné ----------

    async def _ohlas_pad(self, exc: BaseException) -> None:
        """Povie majiteľovi, že modelka spadla. Nikdy nehádže.

        Riadené ukončenie (deploy, presun tenanta) sa NEHLÁSI — to nie je
        porucha a klient by dostával správu pri každom nasadení.
        """
        if self._stopping.is_set() or self._control is None:
            return
        try:
            from credits import OutOfCredits

            # Vyčerpaný kredit hlási `credits.py` vlastnou správou, ktorá povie
            # aj čo s tým. Druhá správa o tom istom by len mátla.
            if isinstance(exc, OutOfCredits):
                return

            nastavenia = {}
            with contextlib.suppress(Exception):
                nastavenia = await self._db_for_notify()
            if not nastavenia.get("notify_crash", True):
                return

            await self._control.notify(
                "🔴 *She stopped replying*\n"
                f"Reason: `{type(exc).__name__}`\n\n"
                "Restarting automatically. If this keeps happening you will "
                "stop getting messages until it is fixed."
            )
        except Exception:  # noqa: BLE001 — hlásenie pádu nesmie pád zhoršiť
            log.exception("model %s: pád sa nepodarilo ohlásiť", self.model_id)

    async def _db_for_notify(self) -> dict:
        """Nastavenia bota bez toho, aby sa runner viazal na `db` z `_run_once`."""
        from db import TenantDb

        db = TenantDb(self._transport, self.model_id)
        return await db.control_bot_settings()

    async def _park(self, reason: str) -> None:
        """Odstaví model: zapíše dôvod do `models` a pustí lease."""
        with contextlib.suppress(Exception):
            await self._reg.set_status(self.model_id, "error", reason)
        await self._release()

    async def _release(self) -> None:
        with contextlib.suppress(Exception):
            await self._reg.release(self.model_id)

    async def _start_instagram(self, cfg, g, llm, control=None) -> None:
        """Best-effort rozbehnutie Instagram agenta. Nikdy nehádže.

        Rovnaké pravidlo ako pri Fanvue: tretia platforma nesmie zhodiť
        odpisovanie na prvej. Keď sa nepodarí, modelka beží na Telegrame ďalej
        a v logu je dôvod.
        """
        try:
            from instagram_start import start_instagram

            await start_instagram(cfg, g, self._transport, llm, self._cleanup, control)
        except Exception as exc:  # noqa: BLE001 — Telegram musí bežať aj tak
            log.error(
                "model %s: Instagram agent sa nespustil (%s) — beží bez neho",
                self.model_id, exc,
            )

    async def _start_fanvue(self, cfg, g, llm, control=None) -> None:
        """Best-effort rozbehnutie dozoru nad Fanvue. Nikdy nehádže.

        Dozor (`fanvue_tenant.FanvueSupervisor`) beží celý život tenanta a
        priebežne pozerá na riadok `fanvue`: pripojenie účtu ani prepnutie
        vypínača v dashboarde tak nepotrebuje reštart modelky. Reštart by
        znamenal aj odpojenie Telethon session, čo je cena, ktorú prepnutie
        vypínača nemá stáť.
        """
        try:
            from fanvue_tenant import start_fanvue

            await start_fanvue(cfg, g, self._transport, llm, self._cleanup, control)
        except Exception as exc:  # noqa: BLE001 — Telegram musí bežať aj tak
            log.error(
                "model %s: Fanvue agent sa nespustil (%s) — beží len Telegram",
                self.model_id, exc,
            )

    async def _drain_cleanup(self) -> None:
        """Zruší úlohy a odpojí klientov z `_cleanup`. Voláva sa aj dvakrát."""
        items, self._cleanup = self._cleanup, []
        for item in items:
            with contextlib.suppress(Exception):
                if isinstance(item, asyncio.Task):
                    item.cancel()
                elif hasattr(item, "is_connected"):
                    if item.is_connected():
                        await item.disconnect()
                elif hasattr(item, "close"):
                    await item.close()

    # ---------- skutočný beh ----------

    async def _run_once(self) -> None:
        """Wiring podľa predlohy `main.run()`, ale pre jedného tenanta.

        Importy sú lokálne: `userbot`/`control_bot` sa portujú v Task 12 a
        runner musí byť importovateľný aj bez nich.
        """
        from control_bot import ControlBot
        from credits import MeteredLlm
        from db import TenantDb
        from llm import Llm
        from userbot import Reconciler, UserBot

        cfg, g = self._cfg, self._g
        # Kľúč je globálny (env), nie tenantov — `TenantDb` ho potrebuje len na
        # dešifrovanie ElevenLabs kľúča, viď hlavičku `db.py`. `account_id` je
        # to, čím si ten kľúč nájde: od migrácie 017 sedí na účte a `TenantDb`
        # ho drží v cache s krátkym TTL, nie v `TenantConfig` — inak by sa
        # prekľúčovanie v dashboarde prejavilo až reštartom modelky, a reštart
        # znamená odpojenie Telethon session.
        db = TenantDb(self._transport, cfg.model_id, g.encryption_key, cfg.account_id,
                      g.platform_eleven_key)
        raw_llm = Llm(
            g.llm_key, g.model, g.summary_model, g.llm_base_url, g.reasoning_effort,
            g.vision_model, g.audio_model,
        )

        # `flood_sleep_threshold=0` je zámerné a dôležité.
        #
        # Telethon má default 60: každý FloodWait do minúty si SÁM odspí
        # a zopakuje. Do našich logov, do flood pauzy ani k majiteľovi sa
        # nedostane nič — účet dostáva varovania a my o nich nevieme. Pritom
        # drobné floody sú presne to včasné varovanie pred tým veľkým.
        #
        # S nulou vyletí každý FloodWait ako výnimka a prejde `_note_flood`,
        # ktorý pauzu rešpektuje do sekundy. Podmienkou je, že žiadna cesta
        # odosielania ho neprehltne — to rieši predchádzajúci commit.
        user_client = TelegramClient(
            StringSession(cfg.tg_session), cfg.tg_api_id, cfg.tg_api_hash,
            flood_sleep_threshold=0,
        )
        # Kontrolný bot píše iba Marekovi, takže tam je auto-sleep neškodný
        # a naopak žiadaný: nechceme, aby sa menu rozsypalo kvôli sekundovej pauze.
        bot_client = TelegramClient(StringSession(), cfg.tg_api_id, cfg.tg_api_hash)
        self._cleanup.extend((user_client, bot_client))

        try:
            # Kontrolný bot je len diaľkové ovládanie. Keď sa neprihlási (typicky
            # FloodWait po viacerých deployoch za sebou), NESMIE to zhodiť
            # odpisovanie — to beží na účte modelky a s botom nemá nič spoločné.
            # Bez tohto crash-loop opakoval prihlásenie a Telegram blokádu predlžoval.
            # Žiadny token nie je porucha, len voľba: kontrolný bot je nepovinný
            # a klient ho smie preskočiť (a dorobiť neskôr v Settings). Preto to
            # ide do logu ako INFO — `log.error` by z bežného stavu robilo alarm
            # a pri hľadaní skutočných porúch by zavádzalo.
            bot_ready = bool(cfg.control_bot_token)
            if not bot_ready:
                log.info(
                    "model %s: bez kontrolného bota (nie je token) — odpisovanie beží ďalej",
                    cfg.model_id,
                )
            else:
                try:
                    await bot_client.start(bot_token=cfg.control_bot_token)
                except Exception as exc:  # noqa: BLE001 - odpisovanie musí bežať aj tak
                    bot_ready = False
                    log.error(
                        "model %s: kontrolný bot sa neprihlásil (%s) — beží len odpisovanie",
                        cfg.model_id, exc,
                    )
            await user_client.connect()
            if not await user_client.is_user_authorized():
                # Predloha tu hádzala RuntimeError s návodom; tu musí ísť von
                # typ, ktorý `run()` rozpozná ako „netreba skúšať znova".
                log.error(
                    "model %s: TG_SESSION nie je platná — vygeneruj novú "
                    "(python scripts/login.py) a nahraj ju modelu",
                    cfg.model_id,
                )
                raise AuthKeyUnregisteredError(request=None)

            control = ControlBot(cfg, db, bot_client)
            # Runner si bota drží, aby vedel ohlásiť pád. Klient sa v `finally`
            # odpojí, takže samotné odoslanie musí prebehnúť SKÔR — viď
            # `_ohlas_pad` volané ešte pred prepadnutím výnimky von.
            self._control = control
            if bot_ready:
                control.register()

            # Každé LLM volanie ide cez merač — bez kreditu sa neodpisuje.
            # Merač sa stavia až tu, aby vedel o vyčerpanom kredite rovno
            # napísať majiteľovi cez kontrolného bota (keď beží).
            llm = MeteredLlm(
                raw_llm, self._reg, cfg.model_id, g.model, g.fallback_price_per_mtok,
                notify=control.notify if bot_ready else None,
            )

            # Skúšobný chat v botovi používa ten istý merač ako odpisovanie.
            control.set_llm(llm)

            userbot = UserBot(cfg, db, llm, user_client, control.notify)
            userbot.register()
            # Semi-auto: prepoj control bota (schvaľovanie) s userbotom
            # (doručovanie). Bez bežiaceho bota semi-auto len necháva čakať.
            if bot_ready:
                userbot.set_control(control)
                control.register_sender("telegram", userbot)
                await control.recover_cards()
                # Modré tlačidlo „Menu" pri vstupe = zoznam príkazov bota.
                # Nastavuje sa raz po štarte; zlyhanie si rieši samo vnútri.
                await control.nastav_prikazy()
            sweeper = userbot.start_sweeper()
            voice_jobs = userbot.start_voice_jobs()
            fallback = control.start_fallback_poller() if bot_ready else None
            self._cleanup.extend(t for t in (sweeper, voice_jobs, fallback) if t)

            # Fanvue je druhá platforma, nie podmienka tejto. Rovnaké pravidlo
            # ako pri kontrolnom bote vyššie: keď sa nepodarí, beží ďalej aspoň
            # odpisovanie na Telegrame. Vlastný `run()` agenta si pády kôl
            # rieši sám, toto chráni pred pádom pri ŠTARTE (nedostupná DB,
            # poškodený token, chýbajúca appka).
            await self._start_fanvue(cfg, g, llm, control if bot_ready else None)
            await self._start_instagram(cfg, g, llm, control if bot_ready else None)

            # Po výpadku dotiahni, čo ušlo — nikomu sa nepíše, len sa doplní
            # kontext a rozhodne, na čo sa ešte oplatí odpovedať.
            reconciler = Reconciler(userbot, cfg, db, user_client)
            caught_up = await reconciler.run()

            me = await user_client.get_me()
            handle = f"@{me.username}" if me.username else me.first_name
            log.info("model %s: beží na účte %s, LLM %s", cfg.model_id, handle, g.model)
            summary = ""
            if caught_up.get("dotiahnutych"):
                summary = (
                    f"\n\nAfter the gap: {caught_up['dotiahnutych']} missed messages, "
                    f"{caught_up['na_odpoved']} to answer"
                )
                if caught_up.get("prestarnutych"):
                    summary += f", {caught_up['prestarnutych']} too old (skipped)"
            if bot_ready:
                # Táto správa chodí pri KAŽDOM nasadení a pri každom presune
                # tenanta medzi replikami — pri častých deployoch je to
                # najhlučnejšia notifikácia zo všetkých, preto sa dá vypnúť.
                try:
                    nastavenia = await db.control_bot_settings()
                except Exception:  # noqa: BLE001 — štart nesmie padnúť na nastaveniach
                    nastavenia = {}
                if nastavenia.get("notify_startup", True):
                    await control.notify(
                        f"🚀 *AI replying is live*\nAccount: {handle}\n"
                        f"Model: `{g.model}`{summary}"
                    )

            # Predloha čakala `asyncio.gather(run_until_disconnected...)`. Tu
            # musí beh skončiť aj na `stop()` (odobratý lease, SIGTERM), preto
            # sa čaká na PRVÚ z: odpojený klient / požiadavka na koniec.
            watchers = [asyncio.create_task(user_client.run_until_disconnected())]
            if bot_ready:
                watchers.append(asyncio.create_task(bot_client.run_until_disconnected()))
            watchers.append(asyncio.create_task(self._stopping.wait()))
            try:
                await asyncio.wait(watchers, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for w in watchers:
                    w.cancel()
                await asyncio.gather(*watchers, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — len ohlásime a pustíme ďalej
            # Ohlásiť sa MUSÍ tu: o pár riadkov nižšie `finally` odpojí bota a
            # potom už niet čím poslať správu. Samotné zotavenie rieši `run()`,
            # tu sa logika behu nemení.
            await self._ohlas_pad(exc)
            raise
        finally:
            # `transport` ani `db` sa tu nezatvárajú — spojenie je spoločné pre
            # všetkých tenantov a patrí poolu (main.py).
            await self._drain_cleanup()
            with contextlib.suppress(Exception):
                await raw_llm.close()
