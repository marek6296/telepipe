"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2 } from "lucide-react";

import { setModelStatusAction } from "@/app/app/actions";
import { setContactRuleAction } from "@/app/app/m/[id]/telegram/actions";
import { Switch } from "@/components/app/forms/fields";
import { TelegramBlock } from "@/components/app/telegram/block";
import { Field } from "@/components/app/telegram/field";
import { ActivateGuide } from "@/components/app/telegram/guides";
import { Callout } from "@/components/app/ui";
import { asStatus, canActivate, canPause, statusReasonText } from "@/lib/status";
import { checkChatId } from "@/lib/telegram-setup";

/**
 * BLOK 1 — JEJ telegramový účet. Jediná povinná vec na tejto stránke.
 *
 * Nesie dve otázky, ktoré si klient kladie ako jednu: „je prihlásená?" a „beží?".
 * Sú to naozaj dve veci (prihlásený účet vie ležať vypnutý), ale patria k tomu
 * istému účtu, takže sú v jednom bloku a nie v dvoch — a nie v inom tabe, kde ich
 * treba hľadať.
 *
 * Znovupripojenie vracia sprievodcu cez `?reconnect=1`. Je to jediný spôsob, ako
 * sa dostať k prvým trom krokom, keď je už raz prihlásená — a zároveň to znamená,
 * že adresa toho stavu existuje a dá sa poslať klientovi odkazom.
 */
export function AccountBlock({
  modelId,
  modelName,
  status,
  statusReason,
  phone,
  skipContacts,
  contactExceptions,
  index,
}: {
  modelId: string;
  modelName: string;
  status: string;
  statusReason: string;
  phone: string | null;
  /** `models.skip_contacts` — nepíše ľuďom, ktorých má účet v kontaktoch. */
  skipContacts: boolean;
  /** `models.contact_exceptions` — koho pustiť aj tak. */
  contactExceptions: number[];
  index?: number;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const value = asStatus(status);
  const live = value === "active";
  const reason = statusReasonText(statusReason);

  const setStatus = (next: "active" | "paused") => {
    setError(null);
    startTransition(async () => {
      const result = await setModelStatusAction(modelId, next);
      if (result.error) {
        setError(result.error);
        return;
      }
      router.refresh();
    });
  };

  const statusLabel = live
    ? "Connected and answering"
    : value === "paused"
      ? "Connected, currently paused"
      : value === "error"
        ? "Connected, but she stopped"
        : "Connected, not switched on yet";

  return (
    <TelegramBlock
      index={index}
      title="Her Telegram account"
      status={live ? "on" : "waiting"}
      statusLabel={statusLabel}
      statusDetail={phone ? `signed in as ${phone}` : "her account is signed in"}
      unlocks="The account the agent runs on. She reads and answers every fan from here, day and night. Everything else on this page is optional; this is not."
      action={
        <>
          {canActivate(value, statusReason) && (
            <button
              type="button"
              onClick={() => setStatus("active")}
              disabled={pending}
              className="app-btn app-btn-primary h-9 px-4"
            >
              {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {value === "paused" ? "Resume" : `Switch ${modelName} on`}
            </button>
          )}
          {canPause(value) && (
            <button
              type="button"
              onClick={() => setStatus("paused")}
              disabled={pending}
              className="app-btn app-btn-ghost h-9 px-4"
            >
              {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Pause
            </button>
          )}
          <Link href="?reconnect=1" className="app-btn app-btn-ghost h-9 px-4">
            Reconnect
          </Link>
        </>
      }
    >
      {error && (
        <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
          {error}
        </Callout>
      )}

      {reason && !live && <Callout tone="danger">{reason}</Callout>}

      <p className="text-[12.5px] leading-relaxed text-[var(--app-text-2)]">
        {live
          ? "She answers new messages from now on, at a human pace. Who she is and how she writes lives on the Persona tab; the caps that keep this account off Telegram's radar are one click away in Settings."
          : "She is signed in but not replying to anyone. Switching her on takes about half a minute — nothing signs in again."}
      </p>

      <ContactRule
        modelId={modelId}
        skipContacts={skipContacts}
        exceptions={contactExceptions}
      />

      <ActivateGuide />
    </TelegramBlock>
  );
}

/* -------------------------------------------------------------------------- */
/*  Kontaktový filter                                                          */
/* -------------------------------------------------------------------------- */

/**
 * „Smie písať jej vlastným kontaktom?"
 *
 * PREČO JE TO VIDNO, A PREČO PRÁVE TU. Marekovmu kamarátovi modelka
 * neodpovedala, kým Marekovi odpovedala — bol v jej kontaktoch a filter ho ticho
 * preskakoval. Nikde v produkte pritom nebolo napísané, že taký filter existuje;
 * hodnota žila v premennej prostredia repliky, spoločnej pre všetkých klientov.
 * Test klienta preto vyzeral ako pokazený produkt. Odteraz je to nastavenie
 * jedného účtu a stojí pri tom účte, aby sa jeho stav dal prečítať naraz s ním.
 *
 * Vypínač je formulovaný KLADNE („smie písať kontaktom"), lebo tak sa to číta.
 * V databáze je to obrátene (`skip_contacts`) a prekladá sa to tu, na jednom
 * mieste.
 */
function ContactRule({
  modelId,
  skipContacts,
  exceptions,
}: {
  modelId: string;
  skipContacts: boolean;
  exceptions: number[];
}) {
  const router = useRouter();
  const [skip, setSkip] = useState(skipContacts);
  const [list, setList] = useState<number[]>(exceptions);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const save = (next: { skipContacts: boolean; exceptions: number[] }) => {
    setError(null);
    // Optimisticky — vypínač aj zoznam musia reagovať okamžite.
    setSkip(next.skipContacts);
    setList(next.exceptions);
    startTransition(async () => {
      const result = await setContactRuleAction(modelId, next);
      if (result.error) {
        setSkip(skipContacts);
        setList(exceptions);
        setError(result.error);
        return;
      }
      router.refresh();
    });
  };

  const addException = () => {
    const check = checkChatId(draft);
    if (!draft.trim() || !check.ok) {
      setError(check.ok ? "Type the number @userinfobot replied with." : check.message);
      return;
    }
    const value = Number(draft);
    if (list.includes(value)) {
      setDraft("");
      return;
    }
    setDraft("");
    save({ skipContacts: skip, exceptions: [...list, value] });
  };

  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-[var(--app-text)]">
            Talk to people already in her contacts
          </p>
          <p
            id="skip-contacts-help"
            className="mt-1 max-w-lg text-[12px] leading-relaxed text-[var(--app-text-3)]"
          >
            Off, anyone saved in this account&apos;s Telegram contacts — her family, her friends —
            gets no reply at all. On, she answers them like any other fan.
          </p>
        </div>
        <Switch
          checked={!skip}
          onCheckedChange={(next) => save({ skipContacts: !next, exceptions: list })}
          disabled={pending}
          label="Talk to people already in her contacts"
          describedBy="skip-contacts-help"
        />
      </div>

      {skip && (
        <div className="mt-3.5 space-y-2.5 border-t border-[var(--app-border)] pt-3.5">
          <p className="text-[12px] leading-relaxed text-[var(--app-text-3)]">
            Exceptions get through anyway. This is how you let one friend test her without opening
            it up to everyone in the contact list.
          </p>

          {list.length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {list.map((id) => (
                <li
                  key={id}
                  className="inline-flex items-center gap-2 rounded-full border border-[var(--app-border)] px-3 py-1 font-mono text-[12px] text-[var(--app-text-2)]"
                >
                  {id}
                  <button
                    type="button"
                    onClick={() =>
                      save({
                        skipContacts: skip,
                        exceptions: list.filter((value) => value !== id),
                      })
                    }
                    disabled={pending}
                    aria-label={`Remove exception ${id}`}
                    className="text-[var(--app-text-4)] transition-colors hover:text-[var(--app-text)]"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12px] text-[var(--app-text-4)]">No exceptions yet.</p>
          )}

          <div className="flex flex-wrap items-end gap-2.5">
            <div className="min-w-[180px] flex-1">
              <Field
                label="Add a chat ID"
                value={draft}
                onChange={(value) => {
                  setDraft(value.replace(/[^\d-]/g, ""));
                  if (error) setError(null);
                }}
                placeholder="6977754097"
                inputMode="numeric"
                mono
                hint="They open @userinfobot in their own Telegram and send you the number it replies with."
              />
            </div>
            <button
              type="button"
              onClick={addException}
              disabled={pending || !draft}
              className="app-btn app-btn-ghost h-10 px-4"
            >
              {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Add
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="mt-3">
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
          </Callout>
        </div>
      )}

      <p className="mt-2.5 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        Changing this picks her up again within half a minute. Her Telegram session is not touched,
        so nothing signs in again.
      </p>
    </div>
  );
}
