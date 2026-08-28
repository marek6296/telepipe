"use server";

import { accountElevenKey, loadVoiceCatalog, type VoiceCatalog } from "@/lib/eleven";
import { getAccount, getModel, requireUser } from "@/lib/models";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import {
  AMBIENCE_LEVEL_MAX,
  AMBIENCE_LEVEL_MIN,
  PREVIEW_TEXT_MAX,
  TEMPO_MAX,
  TEMPO_MIN,
  isAmbience,
  isStrength,
} from "@/lib/voice";

/**
 * Znovunačítanie zoznamu hlasov.
 *
 * Stránka si zoznam ťahá pri renderi, takže toto je len tlačidlo „skús znova" —
 * po prekľúčovaní v nastaveniach účtu alebo keď ElevenLabs práve nešlo.
 *
 * `accountId` sa berie z prihlásenia (`getAccount()`), nikdy z parametra: kľúč
 * sa číta service kľúčom, ktorý obchádza RLS, a jediné, čo tam potom drží
 * cudzie účty od seba, je práve toto.
 */
export async function reloadVoicesAction(): Promise<VoiceCatalog> {
  await requireUser();
  const account = await getAccount();
  if (!account) {
    return { connected: false, voices: [], error: "Your session expired. Sign in again." };
  }
  return loadVoiceCatalog(account.id);
}

/* --------------------------------------------------------------------------
   Štúdio — ukážka hlasovky
--------------------------------------------------------------------------- */
/**
 * Miešanie beží na ffmpegu a ten má worker, nie Vercel. Worker na Railway
 * zase nemá port, takže sa mu nedá zavolať — požiadavka chodí RIADKOM
 * v tabuľke `voice_jobs`, worker si ju do štyroch sekúnd vyzdvihne
 * (`userbot._voice_jobs_once`) a dopíše adresu hotového súboru.
 *
 * Zapisuje sa service kľúčom, lebo rola `authenticated` má na `voice_jobs`
 * grant iba na SELECT (migrácia 007) — a to je správne: v tabuľke je stĺpec
 * `eleven_key`. My ho necháme PRÁZDNY. Worker si kľúč vytiahne sám z účtu
 * (`accounts.eleven_key_enc`, migrácia 017), takže cudzí API kľúč sa cez túto
 * cestu do databázy v čistom texte nikdy nedostane.
 *
 * Service kľúč obchádza RLS, preto `getModel()` NAD ním: to je jediné, čo tu
 * bráni vložiť prácu cudzej modelke.
 */

export type PreviewStart = { error?: string; jobId?: number };

export type PreviewStatus = {
  status: "pending" | "working" | "done" | "error";
  url: string;
  error: string;
};

/** Koľko práce smie naraz čakať. Tlačidlo sa dá držať, fronta nie je nekonečná. */
const MAX_OPEN_JOBS = 3;

export async function startVoicePreviewAction(
  modelId: string,
  input: {
    text: string;
    ambience: string;
    strength: string;
    tempo: number;
    ambience_level: number;
  },
): Promise<PreviewStart> {
  await requireUser();
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  const text = (input.text ?? "").trim();
  if (!text) return { error: "Write what she should say." };
  if (text.length > PREVIEW_TEXT_MAX) {
    return { error: `That is longer than ${PREVIEW_TEXT_MAX} characters — trim it down.` };
  }
  if (!isAmbience(input.ambience)) return { error: "Unknown room." };
  if (!isStrength(input.strength)) return { error: "Unknown recording quality." };

  const tempo = Number(input.tempo);
  if (!Number.isFinite(tempo) || tempo < TEMPO_MIN || tempo > TEMPO_MAX) {
    return { error: `Tempo has to be between ${TEMPO_MIN} and ${TEMPO_MAX}.` };
  }
  const level = Number(input.ambience_level);
  if (!Number.isFinite(level) || level < AMBIENCE_LEVEL_MIN || level > AMBIENCE_LEVEL_MAX) {
    return { error: "Background volume has to be between 0 and 100%." };
  }

  // Bez kľúča a bez hlasu by práca skončila chybou až o pol minúty vo
  // workeri. Obe vieme povedať hneď a klient nečaká na odpoveď, ktorú
  // poznáme dopredu.
  const account = await getAccount();
  if (!account || !(await accountElevenKey(account.id))) {
    return {
      error: "ElevenLabs is not connected on this account. Add the key in Account settings.",
    };
  }

  const supabase = await createClient();
  const { data: behavior } = await supabase
    .from("behavior")
    .select("eleven_voice_id")
    .eq("model_id", model.id)
    .maybeSingle();

  const voiceId = String((behavior as { eleven_voice_id?: string } | null)?.eleven_voice_id ?? "");
  if (!voiceId) return { error: "Pick her voice first — nothing can be spoken without one." };

  // Rozrobená fronta sa počíta cez RLS klienta, nie cez service kľúč: na
  // SELECT grant je (007) a menej ciest okolo RLS je menej ciest, kde sa dá
  // pomýliť v `model_id`.
  const { count } = await supabase
    .from("voice_jobs")
    .select("id", { count: "exact", head: true })
    .eq("model_id", model.id)
    .in("status", ["pending", "working"]);

  if ((count ?? 0) >= MAX_OPEN_JOBS) {
    return { error: "A few previews are still being made. Wait for those first." };
  }

  const admin = createServiceClient();
  const { data, error } = await admin
    .from("voice_jobs")
    .insert({
      model_id: model.id,
      text,
      // Hlas aj kľúč si worker dotiahne sám — hlas z `behavior`, kľúč z účtu.
      // Vypísať ich sem by znamenalo mať cudzí API kľúč v čistom texte
      // v riadku, ktorý si klient smie prečítať.
      voice_id: voiceId,
      ambience: input.ambience,
      strength: input.strength,
      tempo,
      ambience_level: level,
    })
    .select("id")
    .single();

  if (error || !data) return { error: error?.message ?? "Could not queue the preview." };
  return { jobId: Number((data as { id: number }).id) };
}

/**
 * Kam sa práca dostala. Číta sa RLS klientom — `voice_jobs` má na to grant
 * a service kľúč by tu bol zbytočná diera.
 */
export async function voicePreviewStatusAction(
  modelId: string,
  jobId: number,
): Promise<PreviewStatus> {
  await requireUser();
  const supabase = await createClient();
  const { data } = await supabase
    .from("voice_jobs")
    .select("status, url, error")
    .eq("model_id", modelId)
    .eq("id", jobId)
    .maybeSingle();

  if (!data) {
    // Cudzia modelka aj zmazaný riadok vyzerajú rovnako — a to je v poriadku,
    // odpoveď „nič tu nie je" nepovie nič o cudzom účte.
    return { status: "error", url: "", error: "The preview is gone. Generate a new one." };
  }
  const row = data as { status: string; url: string; error: string };
  return {
    status: (["pending", "working", "done", "error"] as const).includes(
      row.status as PreviewStatus["status"],
    )
      ? (row.status as PreviewStatus["status"])
      : "error",
    url: row.url ?? "",
    error: row.error ?? "",
  };
}

/** Posledné ukážky — aby sa dve nastavenia dali porovnať sluchom, nie z pamäte. */
export type PreviewClip = {
  id: number;
  text: string;
  ambience: string;
  strength: string;
  tempo: number;
  url: string;
  /** MP3 verzia na stiahnutie. Prázdne pri starších ukážkach — vtedy OGG. */
  mp3_url: string | null;
  bytes: number | null;
  created_at: string;
};

export async function recentPreviewsAction(
  modelId: string,
  limit = 6,
): Promise<PreviewClip[]> {
  await requireUser();
  const supabase = await createClient();
  const { data } = await supabase
    .from("voice_clips")
    .select("id, text, ambience, strength, tempo, url, mp3_url, bytes, created_at")
    .eq("model_id", modelId)
    .eq("kind", "preview")
    .order("id", { ascending: false })
    .limit(limit);

  return ((data ?? []) as unknown as PreviewClip[]).filter((clip) => clip.url);
}
