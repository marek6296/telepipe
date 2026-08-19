"use server";

import { revalidatePath } from "next/cache";

import { requireUser } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import { notifyAccessRequest } from "@/lib/telegram-admin";

export type ActionResult = { error?: string; ok?: boolean };

/**
 * Žiadosť o prístup.
 *
 * RPC `request_access` je idempotentná, takže opakovaný klik nezaloží druhú
 * žiadosť ani nepošle Marekovi druhú správu do Telegramu.
 */
export async function requestAccessAction(
  _prev: ActionResult | undefined,
  formData: FormData,
): Promise<ActionResult> {
  const user = await requireUser();
  const message = String(formData.get("message") ?? "").trim().slice(0, 1000);

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("request_access", { p_message: message });

  if (error) {
    if (error.message.includes("already unlocked")) {
      return { error: "Your account is already active — reload the page." };
    }
    return { error: "Could not send your request. Please try again." };
  }

  // Telegram je DORUČOVACIA CESTA, nie stav. Keď spadne, žiadosť aj tak stojí
  // v admin paneli — preto sa jeho zlyhanie nesmie dostať k žiadateľovi.
  await notifyAccessRequest({
    requestId: String(data),
    email: user.email ?? "",
    message,
  });

  revalidatePath("/locked");
  return { ok: true };
}
