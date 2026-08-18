"use server";

import { revalidatePath } from "next/cache";

import { saveBehaviorAction } from "@/app/app/m/[id]/persona/behavior/actions";
import { savePersonaAction } from "@/app/app/m/[id]/persona/actions";
import { OUT_OF_CREDITS_MSG, creditState, hasCredit, recordUsage } from "@/lib/credits";
import { chatJson, llmConfigured, llmModel, parseJsonish, type ChatMessage } from "@/lib/llm";
import {
  SYSTEM_PROMPT,
  buildUserMessage,
  mapDraft,
  sanitizeAnswers,
  sanitizeDraft,
  type PersonaDraft,
} from "@/lib/persona-draft";
import { getModel } from "@/lib/models";

/**
 * Asistovaná tvorba persony — jedna akcia na vygenerovanie, jedna na uloženie.
 *
 * PREČO SÚ TO DVE AKCIE: generovanie nič nezapisuje. Klient najprv uvidí, čo mu
 * z odpovedí vzniklo, a až „Apply" to uloží — cez `savePersonaAction` a
 * `saveBehaviorAction`, teda cez tú istú cestu a ten istý whitelist ako
 * obyčajné karty. Do stĺpcov sa odtiaľto nezapisuje priamo nikdy.
 *
 * ČO SA MERIA: každé volanie modelu (aj to, ktoré vrátilo nepoužiteľný JSON)
 * ide do `usage_events` ako `kind='chat'` s reálnou spotrebou — tokeny už
 * zhoreli, nech ich neplatíme my. Rovnaké pravidlo ako `MeteredLlm` vo workeri.
 */

export type GenerateResult = {
  error?: string;
  draft?: PersonaDraft;
  /** Čo sme opravili sami (orezané texty, prehlasovaná pikantnosť…). */
  warnings?: string[];
};

export type ApplyResult = { error?: string; ok?: boolean };

/** Koľkokrát smie model dostať šancu odovzdať použiteľný JSON. */
const TRIES = 2;

export async function generatePersonaDraftAction(
  modelId: string,
  rawAnswers: unknown,
): Promise<GenerateResult> {
  // RLS: cudzie id sa sem nedostane, `getModel` vráti null.
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  const { answers, error } = sanitizeAnswers(rawAnswers);
  if (!answers) return { error: error ?? "Those answers are not complete." };

  if (!llmConfigured()) {
    return { error: "The AI helper is not switched on for this deployment." };
  }

  // Zostatok sa kontroluje PRED volaním — inak by účet bez kreditu vygeneroval
  // personu a dozvedel sa o tom až z faktúry.
  const credit = await creditState();
  if (!hasCredit(credit)) return { error: OUT_OF_CREDITS_MSG };

  const messages: ChatMessage[] = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: buildUserMessage(answers) },
  ];

  let lastProblem = "";

  for (let attempt = 1; attempt <= TRIES; attempt++) {
    const result = await chatJson(messages, { maxTokens: 5000, temperature: 0.85 });

    // Účtujeme vždy, aj pri páde: poskytovateľ si tokeny z každého pokusu berie.
    await recordUsage(model.id, "chat", llmModel(), result.usage);

    if (!result.ok) return { error: result.error ?? "The AI helper did not answer." };

    const parsed = parseJsonish(result.content);
    if (parsed === undefined) {
      lastProblem = "The answer was not valid JSON.";
    } else {
      const mapped = mapDraft(parsed, answers);
      if (mapped.draft) return { draft: mapped.draft, warnings: mapped.warnings };
      lastProblem = mapped.errors.join(" ");
    }

    if (attempt === TRIES) break;

    // Druhý pokus dostane vlastnú chybu späť — bez nej by model zopakoval to
    // isté a klient by zaplatil dve rovnaké odpovede.
    messages.push({ role: "assistant", content: result.content.slice(0, 8000) });
    messages.push({
      role: "user",
      content:
        `That output was rejected: ${lastProblem}\n` +
        "Send the whole JSON object again, corrected. Same keys, nothing else, raw JSON only.",
    });
  }

  return {
    error:
      "The AI helper could not put together a usable persona. Try again, or fill the tabs in yourself.",
  };
}

/**
 * Zápis draftu. Prichádza z prehliadača, takže sa validuje znova — a potom
 * ešte raz v samotných save akciách. UI nie je hranica.
 */
export async function applyPersonaDraftAction(
  modelId: string,
  rawDraft: unknown,
): Promise<ApplyResult> {
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  const { draft, error } = sanitizeDraft(rawDraft);
  if (!draft) return { error: error ?? "There is nothing to apply." };

  const persona = await savePersonaAction(model.id, draft.persona);
  if (persona.error) return { error: persona.error };

  const behavior = await saveBehaviorAction(model.id, draft.behavior);
  if (behavior.error) return { error: behavior.error };

  revalidatePath("/app", "layout");
  return { ok: true };
}
