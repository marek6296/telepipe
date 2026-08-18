"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { saveControlBotAction } from "@/app/app/m/[id]/telegram/actions";
import { Field } from "@/components/app/telegram/field";
import { BotFatherGuide, OwnerChatGuide } from "@/components/app/telegram/guides";
import { Callout, Card, CardHeader } from "@/components/app/ui";

/**
 * Kontrolný bot — token a chat id majiteľa.
 *
 * Bývalo to štvrtým krokom sprievodcu na karte Connection. Sprievodca ale
 * pripája ÚČET modelky; bot je diaľkové ovládanie majiteľa a mení sa aj rok po
 * spustení (nový bot, nový telefón, iné chat id). Preto sedí v nastaveniach,
 * kde sa dá kedykoľvek otvoriť, a nie v kroku, ktorý sa po pripojení už nikdy
 * neukáže.
 *
 * Token sa do políčka NIKDY nepredvyplní — je šifrovaný a von už nejde. Prázdne
 * pole preto znamená „nechaj ten, čo tam je", nie „zmaž ho"; to isté rozlíšenie
 * robí `saveControlBotAction`.
 */
export function ControlBotForm({
  modelId,
  ownerChatId,
  alreadySaved,
}: {
  modelId: string;
  ownerChatId: string;
  alreadySaved: boolean;
}) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [chatId, setChatId] = useState(ownerChatId);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const save = () => {
    setError(null);
    setSaved(null);
    startTransition(async () => {
      const result = await saveControlBotAction({ modelId, token, ownerChatId: chatId });
      if (result.error) {
        setError(result.error);
        return;
      }
      setToken("");
      setSaved(result.detail ? `Saved — ${result.detail} is your control bot.` : "Saved.");
      router.refresh();
    });
  };

  return (
    <Card>
      <CardHeader
        title="Your control bot"
        description="A small Telegram bot that pings you about new fans and lets you take over a chat. She replies to fans without it — you just would not hear about them."
      />
      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-5">
          <div>
            <p className="app-group-label mb-2.5">Create the bot</p>
            <BotFatherGuide />
          </div>
          <div>
            <p className="app-group-label mb-2.5">Find your chat ID</p>
            <OwnerChatGuide />
          </div>
        </div>

        <div className="space-y-4">
          {alreadySaved && (
            <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
              A token is already saved. Leave this empty to keep it — you only need to
              paste one if you replaced the bot.
            </Callout>
          )}
          <Field
            label="Bot token"
            value={token}
            onChange={setToken}
            placeholder={alreadySaved ? "Leave empty to keep the saved token" : "123456789:AAE…"}
            mono
            type="password"
          />
          <Field
            label="Your chat ID"
            value={chatId}
            onChange={(value) => setChatId(value.replace(/[^\d-]/g, ""))}
            placeholder="566608217"
            inputMode="numeric"
          />

          {error && (
            <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
              {error}
            </Callout>
          )}
          {saved && !error && (
            <Callout tone="success" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
              {saved}
            </Callout>
          )}

          <button
            type="button"
            onClick={save}
            // Keď je token už uložený, stačí chat id — inak sa jedno číslo
            // nedalo opraviť bez opätovného vylepenia tokenu, ktorý sa
            // do políčka nikdy nepredvyplní.
            disabled={pending || (!token && !alreadySaved) || !chatId}
            className="app-btn app-btn-primary h-10 w-full"
          >
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            Save control bot
          </button>
          <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            The token is encrypted before it touches our database, and it never leaves the
            server again.
          </p>
        </div>
      </div>
    </Card>
  );
}
