import { toNumber } from "@/lib/format";

/**
 * Spotreba. Klient vidí VÝHRADNE `charged_usd` — `atlas_cost_usd` je naša
 * nákupná cena a do UI sa nesmie dostať (a RLS ho síce pustí, ale my ho
 * nikdy nevyberáme).
 */

export const USAGE_COLUMNS =
  "id, model_id, kind, input_tokens, output_tokens, unit_count, charged_usd, created_at";

export type UsageEvent = {
  id: number;
  model_id: string;
  kind: string;
  input_tokens: number;
  output_tokens: number;
  unit_count: number;
  charged_usd: number | string;
  created_at: string;
};

export const KIND_LABEL: Record<string, string> = {
  chat: "Replies",
  summary: "Memory summaries",
  vision: "Photos she looked at",
  audio: "Voice notes she listened to",
  voice: "Voice notes she sent",
};

export const KIND_HINT: Record<string, string> = {
  chat: "Every message she writes back.",
  summary: "Rewriting what she remembers about a fan.",
  vision: "Understanding a photo a fan sent her.",
  audio: "Transcribing a fan's voice message.",
  voice: "Generating her own voice message.",
};

/** Odtiene bielej — graf je monochróm, série sa líšia jasom, nie farbou. */
export const KIND_COLOR: Record<string, string> = {
  chat: "#fafafa",
  summary: "#a1a1aa",
  vision: "#d4d4d8",
  audio: "#52525b",
  voice: "#71717a",
};

export type DayBucket = { date: string; label: string; total: number };

/** Súčty po dňoch (UTC) za posledných `days` dní vrátane dneška. */
export function dailyTotals(events: UsageEvent[], days: number): DayBucket[] {
  const buckets = new Map<string, number>();
  const today = new Date();
  const start = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate() - (days - 1),
  );

  for (let index = 0; index < days; index += 1) {
    const date = new Date(start + index * 86_400_000);
    buckets.set(date.toISOString().slice(0, 10), 0);
  }

  for (const event of events) {
    const key = event.created_at.slice(0, 10);
    if (buckets.has(key)) {
      buckets.set(key, (buckets.get(key) ?? 0) + toNumber(event.charged_usd));
    }
  }

  return Array.from(buckets.entries()).map(([date, total]) => ({
    date,
    label: new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    }),
    total,
  }));
}

/** Súčet za posledných N dní. */
export function sumSince(events: UsageEvent[], days: number): number {
  const cutoff = Date.now() - days * 86_400_000;
  return events
    .filter((event) => new Date(event.created_at).getTime() >= cutoff)
    .reduce((sum, event) => sum + toNumber(event.charged_usd), 0);
}

export type KindBucket = {
  kind: string;
  total: number;
  count: number;
  tokens: number;
  units: number;
};

export function byKind(events: UsageEvent[]): KindBucket[] {
  const buckets = new Map<string, KindBucket>();
  for (const event of events) {
    const bucket = buckets.get(event.kind) ?? {
      kind: event.kind,
      total: 0,
      count: 0,
      tokens: 0,
      units: 0,
    };
    bucket.total += toNumber(event.charged_usd);
    bucket.count += 1;
    bucket.tokens += (event.input_tokens ?? 0) + (event.output_tokens ?? 0);
    bucket.units += event.unit_count ?? 0;
    buckets.set(event.kind, bucket);
  }
  return Array.from(buckets.values()).sort((a, b) => b.total - a.total);
}
