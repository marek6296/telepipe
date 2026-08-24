"""Rozbehnutie Instagram agenta pre jedného tenanta.

Rovnaký tvar ako `fanvue_tenant.start_fanvue`, len menší: Instagram nemá vault,
nemá médiá a nepíše prvý, takže netreba dozor s vlastnou slučkou — stačí jedna
úloha, ktorá si sama v každom kole prečíta, či je pripojené a zapnuté.

PREČO SA TO NEROZHODUJE PRI ŠTARTE. Klient pripojí účet alebo prepne vypínač
v dashboarde a nemá kvôli tomu čakať na reštart modelky — reštart by znamenal aj
odpojenie Telethon session, čo je cena, ktorú prepnutie vypínača nemá stáť.
Agent preto beží stále a v kole sa pýta.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)


async def start_instagram(cfg, g, transport, llm, cleanup: list, control=None) -> Optional[asyncio.Task]:
    """Pustí Instagram agenta. `None` = tenant ho nemá prečo mať.

    Nič sa tu nechytá: volajúci (runner) to obaľuje `try/except` presne ako
    kontrolného bota — Instagram nesmie zhodiť odpisovanie na Telegrame.
    """
    from instagram_agent import InstagramAgent
    from instagram_tenant import TenantInstagramDb

    db = TenantInstagramDb(transport, cfg.model_id, getattr(g, "encryption_key", ""))

    # Jediný dotaz pri štarte: má vôbec zmysel držať slučku? Nepripojená
    # modelka by inak každých 45 sekúnd chodila do databázy pre nič.
    try:
        nastavenia = await db.settings()
    except Exception as exc:  # noqa: BLE001 — Telegram musí bežať aj tak
        log.warning("model %s: Instagram sa nedá prečítať (%s)", cfg.model_id, exc)
        return None

    if not nastavenia.get("connected"):
        log.info("model %s: Instagram nie je pripojený", cfg.model_id)
        return None

    agent = InstagramAgent(db, llm, control=control)
    uloha = asyncio.create_task(agent.run())
    cleanup.append(uloha)
    log.info(
        "model %s: Instagram agent beží ako @%s",
        cfg.model_id,
        nastavenia.get("username") or "?",
    )
    return uloha
