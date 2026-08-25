/**
 * Volanie LLM z webu. SERVER ONLY — kľúč `LLM_API_KEY` sa nikdy nesmie dostať
 * do prehliadača, takže tento modul smie importovať len server action.
 *
 * Je to ten istý poskytovateľ a ten istý model ako vo workeri
 * (`worker/src/config.py`): OpenAI-kompatibilné `/chat/completions` na Atlase.
 * Defaulty sú zámerne rovnaké konštanty, nie „nejaké" — keby sa rozišli,
 * účtovanie by sa počítalo z ceny iného modelu, než ktorý naozaj odpovedal.
 *
 * SPOTREBA SA SČÍTAVA CEZ POKUSY
 * ------------------------------
 * Po 429/5xx opakujeme, a poskytovateľ si tokeny z každého pokusu účtuje. Preto
 * `usage` chodí von aj z neúspešného volania — presne ako `Llm._chat` vo workeri.
 * Volajúci ho zaúčtuje vždy, aj keď odpoveď nakoniec nedorazila.
 */

const DEFAULT_BASE_URL = "https://api.atlascloud.ai/v1";
const DEFAULT_MODEL = "xai/grok-4.5";

/**
 * Na obrázky iný model — Grok ich neberie. Ten istý, aký na videnie fotiek
 * používa worker (`Llm._vision_model`); keby sa rozišli, popis fotky by písal
 * niekto iný než ten, kto ju v chate vidí.
 */
const DEFAULT_VISION_MODEL = "google/gemini-3.5-flash";

/** Reasoning tokeny sa počítajú do `max_tokens` — worker drží „low" z rovnakého dôvodu. */
const DEFAULT_REASONING_EFFORT = "low";

const ATTEMPTS = 3;
const TIMEOUT_MS = 120_000;

export type LlmUsage = { input: number; output: number };

export type LlmResult = {
  ok: boolean;
  content: string;
  /** Spotreba za CELÉ volanie vrátane neúspešných pokusov. Účtuje sa vždy. */
  usage: LlmUsage;
  error?: string;
};

export function llmModel(): string {
  return process.env.LLM_MODEL?.trim() || DEFAULT_MODEL;
}

export function llmVisionModel(): string {
  return process.env.LLM_VISION_MODEL?.trim() || DEFAULT_VISION_MODEL;
}

function llmKey(): string {
  return (
    process.env.LLM_API_KEY?.trim() ||
    process.env.ATLAS_API_KEY?.trim() ||
    process.env.OPENROUTER_API_KEY?.trim() ||
    ""
  );
}

/** Bez kľúča sa asistent ani neponúkne — inak by klient klikal do prázdna. */
export function llmConfigured(): boolean {
  return llmKey().length > 0;
}

function endpoint(): string {
  const base = (process.env.LLM_BASE_URL?.trim() || DEFAULT_BASE_URL).replace(/\/+$/, "");
  return `${base}/chat/completions`;
}

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

/** Kus správy pre model, ktorý vidí. Text a obrázok v jednom poli. */
export type VisionPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

/**
 * Jedno logické volanie s vynúteným JSON výstupom.
 *
 * `response_format: json_object` je len prosba — nie každý model na Atlase ju
 * pozná, a keď ju odmietne (400), zopakujeme volanie bez nej a spoľahneme sa na
 * parsovanie u volajúceho. Nikdy nehádže: chyba je návratová hodnota, aby sa
 * spotreba nestratila spolu s výnimkou.
 */
export async function chatJson(
  messages: ChatMessage[],
  options: { maxTokens?: number; temperature?: number } = {},
): Promise<LlmResult> {
  return callJson(messages, llmModel(), options);
}

/**
 * To isté, ale s obrázkami — a preto iným modelom (`llmVisionModel`).
 *
 * Obrázky sa posielajú ako URL, nie base64: bucket `photos` je verejný, takže
 * model si ich stiahne sám a my nemusíme ťahať megabajty cez server action
 * (a naraziť na 1 MB limit tela).
 */
export async function chatVisionJson(
  system: string,
  parts: VisionPart[],
  options: { maxTokens?: number; temperature?: number } = {},
): Promise<LlmResult> {
  return callJson(
    [
      { role: "system", content: system },
      { role: "user", content: parts as unknown as string },
    ],
    llmVisionModel(),
    options,
  );
}

async function callJson(
  messages: ChatMessage[],
  model: string,
  options: { maxTokens?: number; temperature?: number } = {},
): Promise<LlmResult> {
  const key = llmKey();
  const usage: LlmUsage = { input: 0, output: 0 };
  if (!key) {
    return { ok: false, content: "", usage, error: "The AI helper is not configured." };
  }

  const payload: Record<string, unknown> = {
    model,
    messages,
    max_tokens: options.maxTokens ?? 4000,
    temperature: options.temperature ?? 0.8,
    reasoning_effort: DEFAULT_REASONING_EFFORT,
    response_format: { type: "json_object" },
  };

  let lastError = "The AI helper did not answer.";

  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    let response: Response;
    try {
      response = await fetch(endpoint(), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch {
      lastError = "The AI helper timed out.";
      if (attempt === ATTEMPTS) break;
      await sleep(attempt);
      continue;
    }

    const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    addUsage(usage, data);

    if (response.ok) {
      const content = firstContent(data);
      if (content) return { ok: true, content, usage };
      // Prázdny content pri `finish_reason: length` znamená, že reasoning
      // zjedol celý strop. Worker rieši to isté zdvihnutím limitu.
      lastError = "The AI helper returned an empty answer.";
      payload.max_tokens = Math.min(Number(payload.max_tokens) * 2, 16_000);
      if (attempt === ATTEMPTS) break;
      continue;
    }

    const detail = typeof data.error === "object" ? JSON.stringify(data.error) : "";
    if (response.status === 400 && detail.includes("response_format")) {
      delete payload.response_format;
      lastError = "The AI helper rejected the JSON mode.";
      continue;
    }
    if (response.status === 429 || response.status >= 500) {
      lastError = `The AI helper is busy (${response.status}).`;
      if (attempt === ATTEMPTS) break;
      await sleep(attempt);
      continue;
    }
    return {
      ok: false,
      content: "",
      usage,
      error: `The AI helper refused the request (${response.status}).`,
    };
  }

  return { ok: false, content: "", usage, error: lastError };
}

/**
 * Text → JSON. Model občas zabalí odpoveď do ```json fence alebo prihodí vetu
 * pred ňu; obe sa dajú zachrániť bez druhého volania, ktoré by klienta stálo
 * ďalšie tokeny.
 */
export function parseJsonish(text: string): unknown | undefined {
  const trimmed = text.trim();
  const candidates = [trimmed];

  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced) candidates.push(fenced[1].trim());

  const first = trimmed.indexOf("{");
  const last = trimmed.lastIndexOf("}");
  if (first >= 0 && last > first) candidates.push(trimmed.slice(first, last + 1));

  for (const candidate of candidates) {
    try {
      return JSON.parse(candidate);
    } catch {
      // ďalší kandidát
    }
  }
  return undefined;
}

function firstContent(data: Record<string, unknown>): string {
  const choices = data.choices;
  if (!Array.isArray(choices) || choices.length === 0) return "";
  const message = (choices[0] as Record<string, unknown>)?.message as
    | Record<string, unknown>
    | undefined;
  return typeof message?.content === "string" ? message.content : "";
}

function addUsage(usage: LlmUsage, data: Record<string, unknown>): void {
  const raw = data.usage as Record<string, unknown> | undefined;
  if (!raw) return;
  usage.input += toInt(raw.prompt_tokens);
  usage.output += toInt(raw.completion_tokens);
}

function toInt(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

function sleep(attempt: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 400 * attempt));
}
