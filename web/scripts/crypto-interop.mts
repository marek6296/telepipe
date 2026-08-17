/**
 * Cross-language roundtrip test: web/lib/crypto.ts  ⇄  worker/src/crypto.py
 *
 * Formát tokenu musí sedieť bajt na bajt, inak worker nedešifruje to, čo web
 * zašifroval do tg_login_jobs / models.*_enc.
 *
 * Spustenie:  npm run test:crypto
 * (Node 26 vie .ts spustiť priamo cez type stripping, netreba build krok.)
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { CryptoError, decrypt, encrypt } from "../lib/crypto.ts";

const WORKER_DIR = path.resolve(import.meta.dirname, "../../worker");
const PYTHON = path.join(WORKER_DIR, ".venv/bin/python");

const KEY = process.env.ENCRYPTION_KEY ?? "JoFAPhHkY+0QClNlXm2VoUanwKdZuNJFxrU1qTN0iPY=";

const SAMPLES = [
  "hello telepipe",
  "1AgAOMTQ5LjE1NC4xNjcuNTEBu0fake-telethon-session-string==",
  "+421 900 123 456 · 2FA héslo s diakritikou 🙂",
  "",
];

function python(code: string): string {
  return execFileSync(PYTHON, ["-c", code], {
    cwd: WORKER_DIR,
    encoding: "utf8",
    env: { ...process.env, PYTHONPATH: path.join(WORKER_DIR, "src") },
  }).trim();
}

function assert(condition: boolean, message: string): void {
  if (!condition) {
    console.error(`✗ ${message}`);
    process.exitCode = 1;
    throw new Error(message);
  }
  console.log(`✓ ${message}`);
}

if (!existsSync(PYTHON)) {
  console.error(`Chýba worker venv: ${PYTHON}`);
  process.exit(1);
}

console.log("Key (base64):", KEY);
console.log("Python:", python("import sys; print(sys.version.split()[0])"));
console.log("Node:   ", process.version);
console.log("");

// Plaintexty putujú medzi jazykmi ako base64 — žiadne problémy s quotingom,
// diakritikou ani emoji v shell argumente.
const b64 = (value: string) => Buffer.from(value, "utf8").toString("base64");
const unb64 = (value: string) => Buffer.from(value, "base64").toString("utf8");

// --- 1) TS zašifruje → Python dešifruje -------------------------------------
console.log("── TS encrypt → Python decrypt ──");
for (const sample of SAMPLES) {
  const token = await encrypt(sample, KEY);
  const out = python(
    `import base64
from crypto import decrypt
print(base64.b64encode(decrypt(${JSON.stringify(token)}, ${JSON.stringify(KEY)}).encode()).decode())`,
  );
  assert(
    unb64(out) === sample,
    `python decrypt == ${JSON.stringify(sample).slice(0, 46)}  [token ${token.slice(0, 28)}…]`,
  );
}

// --- 2) Python zašifruje → TS dešifruje -------------------------------------
console.log("\n── Python encrypt → TS decrypt ──");
for (const sample of SAMPLES) {
  const token = python(
    `import base64
from crypto import encrypt
print(encrypt(base64.b64decode(${JSON.stringify(b64(sample))}).decode(), ${JSON.stringify(KEY)}))`,
  );
  const plain = await decrypt(token, KEY);
  assert(
    plain === sample,
    `ts decrypt == ${JSON.stringify(sample).slice(0, 46)}  [token ${token.slice(0, 28)}…]`,
  );
}

// --- 3) Tvar tokenu ----------------------------------------------------------
console.log("\n── Tvar tokenu ──");
const shapeToken = await encrypt("shape check", KEY);
const [nonceB64, ctB64, tagB64] = shapeToken.split(":");
assert(shapeToken.split(":").length === 3, "token má 3 sekcie oddelené ':'");
assert(Buffer.from(nonceB64, "base64").length === 12, "nonce má 12 bajtov");
assert(Buffer.from(tagB64, "base64").length === 16, "tag má 16 bajtov");
assert(
  Buffer.from(ctB64, "base64").length === Buffer.byteLength("shape check"),
  "ciphertext má dĺžku plaintextu (GCM je stream cipher)",
);

// --- 4) Poškodený token a zlý kľúč musia zlyhať na oboch stranách ------------
console.log("\n── Odmietnutie poškodených dát ──");
const tampered = `${nonceB64}:${Buffer.from("tampered!!!").toString("base64")}:${tagB64}`;
let tsRejected = false;
try {
  await decrypt(tampered, KEY);
} catch (err) {
  tsRejected = err instanceof CryptoError;
}
assert(tsRejected, "TS odmietne poškodený ciphertext");

const pyRejected = python(
  `from crypto import decrypt, CryptoError
try:
    decrypt(${JSON.stringify(tampered)}, ${JSON.stringify(KEY)})
    print("NO")
except CryptoError:
    print("YES")`,
);
assert(pyRejected === "YES", "Python odmietne ten istý poškodený ciphertext");

const otherKey = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString(
  "base64",
);
let wrongKeyRejected = false;
try {
  await decrypt(shapeToken, otherKey);
} catch (err) {
  wrongKeyRejected = err instanceof CryptoError;
}
assert(wrongKeyRejected, "TS odmietne token dešifrovaný zlým kľúčom");

console.log("\nVŠETKY CROSS-LANGUAGE TESTY PREŠLI ✓");
