"use client";

import { useState } from "react";
import Link from "next/link";

import type { ControlBotState } from "@/app/app/m/[id]/telegram/actions";
import { AccountBlock } from "@/components/app/telegram/account-block";
import { ControlBotBlock } from "@/components/app/telegram/control-bot-block";
import { PrivateTelegramBlock } from "@/components/app/telegram/private-telegram-block";

/**
 * Telegram, keď je už raz pripojený — TRI BLOKY, nie stepper.
 *
 * PREČO SA STEPPER PO PRIPOJENÍ STRÁCA. Sprievodca má zmysel len raz: kroky
 * 1–3 sú naozaj postupnosť (bez kľúčov niet telefónu, bez telefónu niet kódu).
 * Bot a súkromný Telegram postupnosť nie sú — sú to dva nezávislé stavy, ktoré
 * sa zapínajú aj vypínajú kedykoľvek a v ľubovoľnom poradí. Kým boli krokmi
 * sprievodcu, museli sa „preklikať" a po dokončení zmizli; ich stav sa dal
 * potom hľadať len na podkarte Settings, inými slovami a s inou grafikou.
 * Preto sú tu ako bloky s trvalým stavom, a v Settings ostali len anti-ban
 * stropy — jedna vec, jedno miesto.
 *
 * Stav bota a spárovania drží tento komponent, lebo ho potrebujú OBA bloky
 * naraz (blok 3 sa bez tokenu z bloku 2 nedá použiť). Keby si ho každý držal
 * sám, uloženie tokenu by blok 3 neodomklo, kým klient stránku neobnoví.
 */
export function TelegramOverview({
  modelId,
  modelName,
  status,
  statusReason,
  phone,
  skipContacts,
  contactExceptions,
  controlBot,
}: {
  modelId: string;
  modelName: string;
  status: string;
  statusReason: string;
  phone: string | null;
  skipContacts: boolean;
  contactExceptions: number[];
  controlBot: ControlBotState;
}) {
  const [bot, setBot] = useState(controlBot);

  return (
    <div className="space-y-4">
      <p className="text-[12.5px] leading-relaxed text-[var(--app-text-3)]">
        Three separate things live here. The first one has to be set up; the other two are yours to
        take or leave, and the third one only makes sense once the second exists.
      </p>

      <AccountBlock
        index={1}
        modelId={modelId}
        modelName={modelName}
        status={status}
        statusReason={statusReason}
        phone={phone}
        skipContacts={skipContacts}
        contactExceptions={contactExceptions}
      />

      <ControlBotBlock index={2} modelId={modelId} state={bot} onState={setBot} />

      <PrivateTelegramBlock index={3} modelId={modelId} state={bot} onState={setBot} />

      <div className="flex flex-wrap gap-4 pt-1 text-[12.5px]">
        <Link
          href={`/app/m/${modelId}/persona`}
          className="text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
        >
          Who she is and how she writes →
        </Link>
        <Link
          href={`/app/m/${modelId}/telegram/settings`}
          className="text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
        >
          Anti-ban caps for this account →
        </Link>
      </div>
    </div>
  );
}
