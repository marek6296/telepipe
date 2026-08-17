import { createClient } from "@/lib/supabase/server";
import type { ModelRow } from "@/lib/models";

/**
 * Stav Telegram pripojenia. `models.tg_session_enc` klient nikdy nevidí
 * (žiadny column grant), takže sa pripojenie odvodzuje z fronty `tg_login_jobs`:
 * posledný job vo fáze `done` znamená, že worker session uložil.
 */

/** Viditeľné stĺpce fronty — `select('*')` by skončil „permission denied". */
export const LOGIN_JOB_COLUMNS =
  "id, model_id, account_id, phase, phone, api_id, error, created_at, updated_at, expires_at";

export type LoginJob = {
  id: number;
  model_id: string;
  account_id: string;
  phase:
    | "send_code"
    | "code_sent"
    | "verify_code"
    | "need_password"
    | "verify_password"
    | "done"
    | "error";
  phone: string;
  api_id: number | null;
  error: string;
  created_at: string;
  updated_at: string;
  expires_at: string;
};

export type TelegramConnection = {
  connected: boolean;
  /** Číslo z posledného úspešného prihlásenia (na zobrazenie „Connected as…"). */
  phone: string | null;
  /** Najnovší job — wizard z neho číta, kde v procese sme. */
  latestJob: LoginJob | null;
};

/** Posledný job modelky (akejkoľvek fázy). */
export async function getLatestLoginJob(modelId: string): Promise<LoginJob | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("tg_login_jobs")
    .select(LOGIN_JOB_COLUMNS)
    .eq("model_id", modelId)
    .order("id", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (data as LoginJob | null) ?? null;
}

export async function getTelegramConnection(model: ModelRow): Promise<TelegramConnection> {
  const supabase = await createClient();

  const [latest, done] = await Promise.all([
    supabase
      .from("tg_login_jobs")
      .select(LOGIN_JOB_COLUMNS)
      .eq("model_id", model.id)
      .order("id", { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from("tg_login_jobs")
      .select(LOGIN_JOB_COLUMNS)
      .eq("model_id", model.id)
      .eq("phase", "done")
      .order("id", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);

  const doneJob = (done.data as LoginJob | null) ?? null;
  // Modelka, ktorú už worker niekedy dvihol, session určite má — aj keby jej
  // joby niekto v DB upratal.
  const running = model.status === "active" || model.status === "paused";

  return {
    connected: Boolean(doneJob) || running,
    phone: doneJob?.phone ?? null,
    latestJob: (latest.data as LoginJob | null) ?? null,
  };
}

/** Rýchla verzia pre zoznamy — len áno/nie, jeden dotaz na modelku. */
export async function getConnectedMap(models: ModelRow[]): Promise<Record<string, boolean>> {
  const supabase = await createClient();
  const map: Record<string, boolean> = {};
  for (const model of models) {
    map[model.id] = model.status === "active" || model.status === "paused";
  }

  const pending = models.filter((model) => !map[model.id]);
  if (pending.length === 0) return map;

  const { data } = await supabase
    .from("tg_login_jobs")
    .select("model_id, phase")
    .in(
      "model_id",
      pending.map((model) => model.id),
    )
    .eq("phase", "done");

  for (const row of data ?? []) {
    map[row.model_id as string] = true;
  }
  return map;
}
