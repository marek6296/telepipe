/**
 * AES-256-GCM — TS port `worker/src/crypto.py`.
 *
 * Formát tokenu je BAJT NA BAJT kompatibilný s workerom:
 *   base64(nonce) ":" base64(ciphertext) ":" base64(tag)
 * nonce = 12 B, tag = 16 B. WebCrypto vracia z `encrypt()` spojené
 * `ciphertext || tag`, takže posledných 16 bajtov odrežeme do vlastnej sekcie
 * (Python `AESGCM` robí to isté: `sealed[:-16]`, `sealed[-16:]`).
 *
 * Kľúč (ENCRYPTION_KEY) je server-only — tento modul sa NIKDY nesmie importovať
 * z client komponentu.
 */

export class CryptoError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CryptoError";
  }
}

const NONCE_BYTES = 12;
const TAG_BYTES = 16;

function b64encode(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function b64decode(value: string): Uint8Array {
  const binary = atob(value);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

/** Rovnaká validácia ako v Pythone — base64, presne 32 bajtov. */
async function importKey(keyB64: string): Promise<CryptoKey> {
  let raw: Uint8Array;
  try {
    raw = b64decode(keyB64);
  } catch {
    throw new CryptoError("ENCRYPTION_KEY nie je platný base64");
  }
  if (raw.length !== 32) {
    throw new CryptoError("ENCRYPTION_KEY musí byť 32 bajtov (AES-256)");
  }
  return crypto.subtle.importKey("raw", raw as BufferSource, "AES-GCM", false, [
    "encrypt",
    "decrypt",
  ]);
}

export async function encrypt(plaintext: string, keyB64: string): Promise<string> {
  const key = await importKey(keyB64);
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_BYTES));
  const sealed = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: nonce as BufferSource, tagLength: TAG_BYTES * 8 },
      key,
      new TextEncoder().encode(plaintext) as BufferSource,
    ),
  );
  // WebCrypto pripája tag na koniec — rozdelíme rovnako ako Python
  const ct = sealed.slice(0, sealed.length - TAG_BYTES);
  const tag = sealed.slice(sealed.length - TAG_BYTES);
  return `${b64encode(nonce)}:${b64encode(ct)}:${b64encode(tag)}`;
}

export async function decrypt(token: string, keyB64: string): Promise<string> {
  const key = await importKey(keyB64);

  let nonce: Uint8Array;
  let sealed: Uint8Array;
  try {
    const parts = token.split(":");
    if (parts.length !== 3) throw new Error("bad shape");
    const [nonceB64, ctB64, tagB64] = parts;
    nonce = b64decode(nonceB64);
    const ct = b64decode(ctB64);
    const tag = b64decode(tagB64);
    if (nonce.length !== NONCE_BYTES || tag.length !== TAG_BYTES) {
      throw new Error("bad lengths");
    }
    sealed = new Uint8Array(ct.length + tag.length);
    sealed.set(ct, 0);
    sealed.set(tag, ct.length);
  } catch {
    throw new CryptoError("Poškodený šifrovaný token");
  }

  try {
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: nonce as BufferSource, tagLength: TAG_BYTES * 8 },
      key,
      sealed as BufferSource,
    );
    return new TextDecoder().decode(plain);
  } catch {
    throw new CryptoError("Dešifrovanie zlyhalo — zlý kľúč alebo poškodené dáta");
  }
}

/** Prázdny reťazec necháme prázdny — DB stĺpce majú default ''. */
export async function encryptOptional(
  plaintext: string | null | undefined,
  keyB64: string,
): Promise<string> {
  if (!plaintext) return "";
  return encrypt(plaintext, keyB64);
}
