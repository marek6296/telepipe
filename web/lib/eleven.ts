import { decrypt } from "@/lib/crypto";
import { encryptionKey } from "@/lib/env";
import { createServiceClient } from "@/lib/supabase/server";

/**
 * ElevenLabs — kľúč účtu a zoznam hlasov. SERVER ONLY.
 *
 * Kľúč žije od migrácie 017 na `accounts.eleven_key_enc` a rola `authenticated`
 * naň nemá column grant — ani majiteľ si ho neprečíta. Rozbaliť ho vie len
 * niečo, čo drží `ENCRYPTION_KEY`: worker (`worker/src/db.py`) a tento súbor.
 * Preto sa tu ide service kľúčom, ktorý OBCHÁDZA RLS — a preto sa `accountId`
 * NIKDY nesmie vziať z requestu, len z `auth.uid()` (`getAccount()`).
 *
 * Kontrakt zoznamu hlasov je zhodný s `worker/src/eleven.py:list_voices()`:
 * `GET /v1/voices`, hlavička `xi-api-key`, z odpovede `voices[]`. Prázdny
 * zoznam NIE JE „nemá hlasy" — ElevenLabs vracia každému účtu aspoň
 * predvolené — ale „kľúč nesedí alebo služba nebeží". Ukazuje sa preto ako
 * chyba, nie ako prázdny výber.
 */

const BASE = "https://api.elevenlabs.io/v1";
const TIMEOUT_MS = 15_000;

export type ElevenVoice = {
  id: string;
  name: string;
  /** Priama URL na ukážku (mp3). Prázdna = ukážka nie je. */
  preview: string;
};

export type VoiceCatalog = {
  /** Má účet vôbec pripojený ElevenLabs? */
  connected: boolean;
  voices: ElevenVoice[];
  /** Prázdne = v poriadku. Inak veta pre človeka. */
  error: string;
};

/** Kľúč účtu v čistom texte. Prázdny = účet nie je pripojený. */
export async function accountElevenKey(accountId: string): Promise<string> {
  if (!accountId) return "";

  const admin = createServiceClient();
  const { data, error } = await admin
    .from("accounts")
    .select("eleven_key_enc")
    .eq("id", accountId)
    .maybeSingle();

  if (error || !data?.eleven_key_enc) return "";

  try {
    return await decrypt(data.eleven_key_enc as string, encryptionKey());
  } catch {
    // Nedešifrovateľná šifra znamená rozladený ENCRYPTION_KEY medzi Vercelom
    // a Railway — to je porucha nasadenia, nie vec, ktorú má riešiť používateľ.
    // Von ide „nepripojené"; worker to isté zaloguje ako varovanie.
    return "";
  }
}

/** Hlasy na účte ElevenLabs. Chyby sú v `error`, nie vo výnimke. */
export async function listVoices(apiKey: string): Promise<VoiceCatalog> {
  if (!apiKey) return { connected: false, voices: [], error: "" };

  let payload: unknown;
  try {
    const response = await fetch(`${BASE}/voices`, {
      headers: { "xi-api-key": apiKey },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    if (response.status === 401) {
      return {
        connected: true,
        voices: [],
        error:
          "ElevenLabs rejected the key. Paste a fresh one in Account settings.",
      };
    }
    if (!response.ok) {
      return {
        connected: true,
        voices: [],
        error: `ElevenLabs answered ${response.status}. Try again in a minute.`,
      };
    }
    payload = await response.json();
  } catch {
    return {
      connected: true,
      voices: [],
      error: "Could not reach ElevenLabs. Try again in a minute.",
    };
  }

  const rows = Array.isArray((payload as { voices?: unknown })?.voices)
    ? ((payload as { voices: unknown[] }).voices as Record<string, unknown>[])
    : [];

  const voices = rows
    .filter((row) => typeof row.voice_id === "string" && row.voice_id)
    .map((row) => ({
      id: String(row.voice_id),
      name: String(row.name || "(unnamed)"),
      preview: typeof row.preview_url === "string" ? row.preview_url : "",
    }));

  if (voices.length === 0) {
    return {
      connected: true,
      voices: [],
      error:
        "ElevenLabs returned no voices at all — that means the key is wrong, not that the account is empty.",
    };
  }

  return { connected: true, voices, error: "" };
}

/** Kľúč účtu + jeho hlasy v jednom kroku — to, čo potrebuje karta hlasu. */
export async function loadVoiceCatalog(accountId: string): Promise<VoiceCatalog> {
  return listVoices(await accountElevenKey(accountId));
}
