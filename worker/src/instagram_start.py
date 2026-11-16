"""Rozbehnutie Instagram agenta pre jedného tenanta.

Rovnaký tvar ako `fanvue_tenant.start_fanvue`, len menší: Instagram nemá vault,
nemá médiá a nepíše prvý, takže netreba dozor s vlastnou slučkou — stačí jedna
úloha, ktorá si sama v každom kole prečíta, či je pripojené a zapnuté.

AGENT BEŽÍ VŽDY, AJ BEZ PRIPOJENIA. Klient pripojí účet alebo prepne vypínač
v dashboarde a nemá kvôli tomu čakať na reštart modelky — reštart by znamenal aj
odpojenie Telethon session, čo je cena, ktorú prepnutie vypínača nemá stáť.
Predtým sa tu pri štarte pýtalo „je pripojený?" a nepripojená modelka agenta
vôbec nedostala; účet pripojený neskôr potom mlčal až do najbližšieho deployu.
Nepripojený agent sa pozerá do databázy len raz za pár minút
(`instagram_agent.NECINNE_S`), takže to nič nestojí.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)


async def start_instagram(cfg, g, transport, llm, cleanup: list, control=None) -> Optional[asyncio.Task]:
    """Pustí Instagram agenta a zaregistruje ho v control bote (semi karty).

    Nič sa tu nechytá: volajúci (runner) to obaľuje `try/except` presne ako
    kontrolného bota — Instagram nesmie zhodiť odpisovanie na Telegrame.
    """
    from instagram_agent import InstagramAgent
    from instagram_tenant import TenantInstagramDb

    db = TenantInstagramDb(transport, cfg.model_id, getattr(g, "encryption_key", ""))
    agent = InstagramAgent(db, llm, control=control)
    if control is not None:
        # Kliky na Instagram kartách (schváliť, Regenerate, Context, Take over)
        # doručuje control bot cez tohto agenta.
        control.register_sender("instagram", agent)
        # The runner initially restores cards before channel senders exist.
        # Now IG can retire cancelled/expired actions left by older versions.
        await control.recover_cards()

    uloha = asyncio.create_task(agent.run())
    cleanup.append(uloha)
    log.info("model %s: Instagram agent beží (pripojenie sa kontroluje v každom kole)", cfg.model_id)
    return uloha
