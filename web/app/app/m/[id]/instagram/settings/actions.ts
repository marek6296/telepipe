"use server";

import { getViewerRole } from "@/lib/admin";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

/**
 * Nastavenia Instagram agenta.
 *
 * Whitelist je tu preto, aby sa cez patch nedal poslať `connected`, `enabled`
 * ani token — to sú veci servera. Skutočnú hranicu drží stĺpcový grant
 * v databáze (klient na ne `UPDATE` nemá), toto je prvá z dvoch.
 *
 * Rola sa overuje ZNOVA: karta je zatiaľ len pre superadmina a server action
 * sa dá zavolať aj bez toho, aby si ju niekto otvoril.
 */
export type InstagramSettingsResult = { error?: string };

const ENUMY: Record<string, readonly string[]> = {
  funnel_target: ["telegram", "bio_link"],
  reply_mode: ["off", "auto", "semi"],
  // `hot` tu nie je a nebude: na Instagrame je to cesta k zrušeniu účtu.
  heat: ["mild", "medium"],
};

const BOOLEANY = ["reply_comments"] as const;

/** Telegramové meno bez zavináča, tak ako ho Telegram naozaj používa. */
const HANDLE_RE = /^[a-zA-Z][a-zA-Z0-9_]{4,31}$/;
const LINK_RE = /^https?:\/\/\S+\.\S+/;

export async function saveInstagramSettingsAction(
  modelId: string,
  patch: Record<string, unknown>,
): Promise<InstagramSettingsResult> {
  await requireModelSubTab(modelId, "instagram", "settings");
  if ((await getViewerRole()) !== "superadmin") {
    return { error: "Instagram is not available on your account yet." };
  }

  const update: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(patch)) {
    if (key in ENUMY) {
      const text = String(value ?? "");
      if (!ENUMY[key].includes(text)) return { error: `Unexpected value for ${key}.` };
      update[key] = text;
      continue;
    }
    if ((BOOLEANY as readonly string[]).includes(key)) {
      update[key] = Boolean(value);
      continue;
    }
    if (key === "telegram_handle") {
      // Zavináč si ľudia píšu aj nepíšu — berieme oboje a uložíme bez neho.
      const handle = String(value ?? "").trim().replace(/^@+/, "");
      if (handle && !HANDLE_RE.test(handle)) {
        return { error: "That is not a Telegram username (5–32 letters, digits or _)." };
      }
      update.telegram_handle = handle;
      continue;
    }
    if (key === "bio_link") {
      const link = String(value ?? "").trim();
      if (link && !LINK_RE.test(link)) {
        return { error: "The link must start with https:// and look like a real URL." };
      }
      // Odkaz na platenú platformu sem nepatrí — práve pred tým to má chrániť.
      if (/fanvue\.com|onlyfans\.com/i.test(link)) {
        return {
          error:
            "Do not point Instagram at Fanvue or OnlyFans directly — that is what gets accounts banned. Use a link page (Linktree, linkovne.com) instead.",
        };
      }
      update.bio_link = link;
      continue;
    }
    return { error: `Unknown setting: ${key}` };
  }

  if (Object.keys(update).length === 0) return {};
  update.updated_at = new Date().toISOString();

  const supabase = await createClient();
  const { error } = await supabase
    .from("instagram")
    .update(update)
    .eq("model_id", modelId);

  if (error) return { error: error.message };
  return {};
}
