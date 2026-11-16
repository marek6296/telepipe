"use server";

import { revalidatePath } from "next/cache";
import { getViewerRole } from "@/lib/admin";
import { requireModelSubTab } from "@/lib/models";
import { createServiceClient } from "@/lib/supabase/server";
import { validateInstagramPatch } from "@/lib/instagram-policy";

export type InstagramSettingsResult = { error?: string; message?: string };

async function owner(modelId: string) {
  await requireModelSubTab(modelId, "instagram", "settings");
  if ((await getViewerRole()) !== "superadmin") throw new Error("Instagram is not available on your account yet.");
  return createServiceClient();
}

export async function saveInstagramSettingsAction(modelId: string, patch: Record<string, unknown>): Promise<InstagramSettingsResult> {
  const db = await owner(modelId);
  const parsed = validateInstagramPatch(patch);
  if (parsed.error || !parsed.update) return {error: parsed.error};
  const update = parsed.update;
  if (!Object.keys(update).length) return {};
  // One visible mode controls the legacy enabled flag too; Off is a real stop.
  if (typeof update.reply_mode === "string") update.enabled = update.reply_mode !== "off";
  update.updated_at = new Date().toISOString();
  const {error} = await db.from("instagram").update(update).eq("model_id", modelId);
  if (error) return {error: error.message};
  revalidatePath(`/app/m/${modelId}/instagram/settings`);
  return {};
}

export async function manageInstagramAction(modelId: string, operation: string, value: string, other = ""): Promise<InstagramSettingsResult> {
  const db = await owner(modelId);
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (operation === "verify" || operation === "reject") {
    if (!uuid.test(value) || !uuid.test(other)) return {error: "Choose two valid contact identities."};
    const {data, error} = await db.from("conversation_identities").select("id,platform").eq("model_id", modelId).in("id", [value, other]);
    if (error || data?.length !== 2 || data[0].platform === data[1].platform) return {error: "These identities cannot be linked."};
    const result = await db.rpc("conversation_pair", {p_model: modelId, p_identity: value, p_other: other,
      p_decision: operation === "verify" ? "verified" : "rejected", p_evidence: {reason: "owner_review"}});
    if (result.error) return {error: result.error.message};
  } else if (operation === "resume") {
    if (!/^\d{1,40}$/.test(value)) return {error: "Invalid contact."};
    const {error} = await db.from("ig_users").update({human_takeover: false, ai_enabled: true}).eq("model_id", modelId).eq("igsid", value);
    if (error) return {error: error.message};
  } else if (operation === "test") {
    const username = value.trim().replace(/^@/, "").toLowerCase();
    if (!/^[a-z0-9_.]{1,30}$/.test(username)) return {error: "Enter an Instagram username."};
    const {data, error} = await db.from("ig_users").select("igsid").eq("model_id", modelId).ilike("username", username.replaceAll("_", "\\_"));
    if (error || data?.length !== 1) return {error: "Send a DM from that account and let the history import finish first."};
    const saved = await db.from("instagram").update({test_igsid: data[0].igsid, test_until: new Date(Date.now()+2*3600_000).toISOString()}).eq("model_id", modelId);
    if (saved.error) return {error: saved.error.message};
  } else if (operation === "end_test") {
    const {error} = await db.from("instagram").update({test_igsid: "", test_until: null}).eq("model_id", modelId);
    if (error) return {error: error.message};
  } else if (operation === "photo") {
    if (!/^\d+$/.test(value)) return {error: "Choose an existing photo."};
    const {data, error} = await db.from("photos").select("id,url").eq("model_id", modelId).eq("id", value).eq("active", true).eq("spicy", false).maybeSingle();
    if (error || !data || !String(data.url).startsWith("https://")) return {error: "Choose an active SFW photo with an HTTPS URL."};
    const cleared = await db.from("photos").update({instagram_approved: false}).eq("model_id", modelId);
    if (cleared.error) return {error: cleared.error.message};
    const saved = await db.from("photos").update({instagram_approved: true}).eq("model_id", modelId).eq("id", value);
    if (saved.error) return {error: saved.error.message};
  } else return {error: "Unknown action."};
  revalidatePath(`/app/m/${modelId}/instagram/settings`);
  return {message: operation === "resume" ? "Resumed for the next incoming message." : "Saved."};
}
