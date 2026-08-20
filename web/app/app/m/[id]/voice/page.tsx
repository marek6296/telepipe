import type { Metadata } from "next";

import { recentPreviewsAction } from "@/app/app/m/[id]/voice/actions";
import { VoiceForm, type VoiceRow } from "@/components/app/voice-form";
import { VoiceSource, type ManagedVoiceOption } from "@/components/app/voice-source";
import { VoiceStudio } from "@/components/app/voice-studio";
import { Callout, PageHeader } from "@/components/app/ui";
import { loadVoiceCatalog } from "@/lib/eleven";
import { getAccount, requireModelTab } from "@/lib/models";
import { getAppConfig } from "@/lib/slots";
import { createClient } from "@/lib/supabase/server";
import { toNumber } from "@/lib/format";
import {
  AMBIENCE_DEFAULT,
  AMBIENCE_LEVEL_DEFAULT,
  STRENGTH_DEFAULT,
  TEMPO_DEFAULT,
} from "@/lib/voice";

export const metadata: Metadata = {
  title: "Voice",
};

/**
 * Hlasové stĺpce tabuľky `behavior`. `eleven_key*` medzi nimi nie je a ani
 * nemôže byť — klient naň nemá column grant (007/014) a od 017 kľúč sedí na
 * účte, nie na modelke.
 */
const VOICE_COLUMNS =
  "model_id, voices_enabled, eleven_voice_id, voice_ambience, voice_strength, " +
  "voice_chance, voice_tempo, voice_ambience_level, voice_when_asked, " +
  "voice_when_doubted, voice_when_he_voices, voice_when_away, " +
  "voice_on_goodnight, voice_when_hot, " +
  // Rozsahy z 029. Grant na ne dostala rola `authenticated` v tej istej
  // migrácii — bez neho by celý tento select spadol na „permission denied",
  // nie len tieto stĺpce.
  "voice_volume_min, voice_volume_max, voice_lead_min, voice_lead_max, " +
  "voice_tail_min, voice_tail_max, " +
  // 20260819160000 — odkial berie hlas (nas katalog vs. klientov kluc).
  "voice_source, managed_voice_id";

export default async function VoicePage({ params }: PageProps<"/app/m/[id]/voice">) {
  const { id } = await params;
  // Model, účet aj klient sú nezávislé — sekvenčne to boli tri okruhy do
  // databázy (~114 ms každý) skôr, než sa vôbec začal čítať riadok `behavior`.
  const [model, account, supabase] = await Promise.all([
    requireModelTab(id, "voice"),
    getAccount(),
    createClient(),
  ]);

  const { data } = await supabase
    .from("behavior")
    .select(VOICE_COLUMNS)
    .eq("model_id", model.id)
    .maybeSingle();

  if (!data) {
    return (
      <Callout tone="danger">
        Her behaviour row is missing. Reload the page, and contact us if it stays empty.
      </Callout>
    );
  }

  const voice = data as unknown as VoiceRow;
  const row = data as unknown as Record<string, unknown>;

  // Katalóg hlasov, náš číselník a cenník naraz — ani jedno nezávisí od
  // druhého. `loadVoiceCatalog` sa ťahá zo servera, nie z prehliadača: kľúč
  // ElevenLabs nesmie opustiť server, ani na jedno GET. RLS pustí len zapnuté
  // hlasy, takže filtrovať tu netreba.
  const [catalog, { data: managed }, config] = await Promise.all([
    loadVoiceCatalog(account?.id ?? ""),
    supabase
      .from("managed_voices")
      .select("id, label, description")
      .order("sort")
      .order("label"),
    getAppConfig(),
  ]);

  // Štúdio má zmysel iba s pripojeným účtom — bez kľúča nie je čím prehovoriť
  // a tlačidlo „Generate" by sľubovalo niečo, čo nemôže vzniknúť.
  const clips = catalog.connected ? await recentPreviewsAction(model.id).catch(() => []) : [];

  return (
    <>
      <PageHeader
        eyebrow="Telegram agent"
        title="Voice"
        description="Voice notes convert better than text — and they are the hardest thing to fake. The ElevenLabs account is connected once in Account settings; here you only pick her voice and how she uses it."
      />
      <div className="mb-5">
        <VoiceSource
          modelId={model.id}
          source={String(row.voice_source ?? "own")}
          managedVoiceId={(row.managed_voice_id as string | null) ?? null}
          voices={(managed ?? []) as ManagedVoiceOption[]}
          managedPriceUsd={config.voice_managed_usd}
          hasOwnKey={catalog.connected}
        />
      </div>

      <VoiceForm
        voice={voice}
        catalog={catalog}
      />
      {catalog.connected && (
        <div className="mt-5">
          <VoiceStudio
            modelId={model.id}
            saved={{
              hasVoice: Boolean(voice.eleven_voice_id),
              ambience: voice.voice_ambience || AMBIENCE_DEFAULT,
              strength: voice.voice_strength || STRENGTH_DEFAULT,
              tempo: toNumber(voice.voice_tempo) || TEMPO_DEFAULT,
              // Nula je platná hodnota (ticho pod hlasom), takže `||` by ju
              // ticho prepísalo na 5 %. Default patrí len chýbajúcemu číslu.
              ambience_level: Number.isFinite(toNumber(voice.voice_ambience_level))
                ? toNumber(voice.voice_ambience_level)
                : AMBIENCE_LEVEL_DEFAULT,
            }}
            clips={clips}
          />
        </div>
      )}
    </>
  );
}
