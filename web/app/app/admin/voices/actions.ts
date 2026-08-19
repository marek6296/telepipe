"use server";

import { revalidatePath } from "next/cache";

import { requireSuperadmin } from "@/lib/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Katalóg NAŠICH hlasov (`managed_voices`) — to, čo si klient môže vybrať
 * namiesto pripájania vlastného ElevenLabs kľúča.
 *
 * Je to obyčajný číselník, takže zápis ide priamo cez RLS (`is_admin()`), nie
 * cez RPC. Autorizácia je aj tak dvakrát: raz tu, raz v politike v DB.
 *
 * Hlasy sú v tabuľke a nie v kóde zámerne: keď ich Marek vymení za nové,
 * mení sa iba `eleven_voice_id`, nie deploy.
 */

export type VoiceResult = { error?: string; ok?: boolean };

export async function saveVoiceAction(
  id: string | null,
  input: { label: string; eleven_voice_id: string; description: string; active: boolean },
): Promise<VoiceResult> {
  await requireSuperadmin();

  const label = input.label.trim();
  const elevenId = input.eleven_voice_id.trim();

  if (label.length < 2) return { error: "Give the voice a name." };
  if (label.length > 40) return { error: "Keep the name under 40 characters." };
  // ElevenLabs voice id je 20 znakov base62. Netestujeme, či hlas na účte
  // naozaj je — to by znamenalo volať ElevenLabs pri každom uložení; strážime
  // len tvar, aby sa do katalógu nedostal odpad z konzoly.
  if (!/^[A-Za-z0-9]{16,40}$/.test(elevenId)) {
    return { error: "That is not an ElevenLabs voice id." };
  }

  const supabase = await createClient();
  const row = {
    label,
    eleven_voice_id: elevenId,
    description: input.description.trim().slice(0, 200),
    active: input.active,
  };

  const { error } = id
    ? await supabase.from("managed_voices").update(row).eq("id", id)
    : await supabase.from("managed_voices").insert(row);

  if (error) return { error: error.message };

  revalidatePath("/app/admin/voices");
  return { ok: true };
}

export async function deleteVoiceAction(id: string): Promise<VoiceResult> {
  await requireSuperadmin();

  const supabase = await createClient();
  const { error } = await supabase.from("managed_voices").delete().eq("id", id);

  if (error) {
    // Na hlas sa môže odkazovať `behavior.managed_voice_id` (FK). Modelke,
    // ktorá ho má vybraný, by zmazanie stíchlo hlasovky — preto radšej
    // poradíme vypnutie, ktoré ju z ponuky odstráni bez rozbitia väzby.
    if (error.message.includes("foreign key") || error.code === "23503") {
      return {
        error:
          "A model is still using this voice. Switch it off instead — it disappears from the picker and keeps working for whoever already has it.",
      };
    }
    return { error: error.message };
  }

  revalidatePath("/app/admin/voices");
  return { ok: true };
}
