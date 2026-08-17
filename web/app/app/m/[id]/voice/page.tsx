import type { Metadata } from "next";

import { VoiceForm, type VoiceRow } from "@/components/app/voice-form";
import { Callout, PageHeader } from "@/components/app/ui";
import { loadVoiceCatalog } from "@/lib/eleven";
import { getAccount, requireModelTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

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
  "voice_on_goodnight, voice_when_hot";

export default async function VoicePage({ params }: PageProps<"/app/m/[id]/voice">) {
  const { id } = await params;
  const model = await requireModelTab(id, "voice");
  const account = await getAccount();

  const supabase = await createClient();
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

  // Zoznam hlasov sa ťahá zo servera pri renderi, nie z prehliadača: kľúč
  // ElevenLabs nesmie opustiť server, ani na jedno GET.
  const catalog = await loadVoiceCatalog(account?.id ?? "");

  return (
    <>
      <PageHeader
        eyebrow="Telegram agent"
        title="Voice"
        description="Voice notes convert better than text — and they are the hardest thing to fake. The ElevenLabs account is connected once in Account settings; here you only pick her voice and how she uses it."
      />
      <VoiceForm
        voice={data as unknown as VoiceRow}
        catalog={catalog}
      />
    </>
  );
}
