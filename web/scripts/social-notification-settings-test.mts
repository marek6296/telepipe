import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";
import ts from "typescript";

const modelId = "10000000-0000-0000-0000-000000000001";
let permitted = true;
const calls: { modelId: string; update: Record<string, unknown> }[] = [];
const mocks: Record<string, unknown> = {
  "@/lib/models": { requireModelSubTab: async (id: string) => { assert.equal(id, modelId); if (!permitted) throw new Error("Forbidden"); } },
  "@/lib/supabase/server": { createClient: async () => ({ from: (table: string) => {
    assert.equal(table, "control_bot_settings");
    return { upsert: async (update: Record<string, unknown>) => { calls.push({ modelId, update }); return { error: null }; } };
  } }) },
};
const path = resolve(import.meta.dirname, "../app/app/m/[id]/telegram/bot/actions.ts");
const source = ts.transpileModule(readFileSync(path, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const loaded = { exports: {} as { saveBotSettingsAction: (modelId: string, patch: Record<string, unknown>) => Promise<{ error?: string }> } };
vm.runInThisContext(`(function(require,module,exports){${source}\n})`, { filename: path })((name: string) => {
  if (!(name in mocks)) throw new Error(`Unexpected import ${name}`);
  return mocks[name];
}, loaded, loaded.exports);
const save = loaded.exports.saveBotSettingsAction;

assert.deepEqual(await save(modelId, { notify_social_inbound: false }), {});
assert.equal(calls.length, 1);
assert.equal(calls[0].update.notify_social_inbound, false, "Opting out must persist false");
assert.equal(calls[0].update.model_id, modelId);
assert.deepEqual(Object.keys(calls[0].update).sort(), ["model_id", "notify_social_inbound", "updated_at"], "Notification changes must leave every legacy flag untouched");
calls.length = 0;
assert.ok((await save(modelId, { notify_social_inbound: "false" })).error, "A truthy string must not silently enable alerts");
assert.ok((await save(modelId, { notify_startup: false })).error, "Old clients cannot write retired alert settings");
assert.equal(calls.length, 0);
permitted = false;
await assert.rejects(save(modelId, { notify_social_inbound: true }), /Forbidden/);
assert.equal(calls.length, 0, "Unauthorized callers cannot mutate notification preferences");
console.log("Social notifications: explicit boolean opt-out, preserved legacy settings and owner guard passed.");
