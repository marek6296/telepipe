const ENUMS: Record<string, readonly string[]> = {
  funnel_target: ["telegram", "bio_link"], reply_mode: ["off", "auto", "semi"], heat: ["mild", "medium"],
};
const BOOLEANS = new Set(["reply_comments", "sync_enabled", "reactions_enabled", "photos_enabled", "highlights_link", "typo_enabled"]);

export function validLinkPage(raw: string): boolean {
  try {
    const url = new URL(raw);
    return raw.length <= 400 && !/\s/.test(raw) && url.protocol === "https:" &&
      ["linkovne.com", "www.linkovne.com"].includes(url.hostname) && !url.username && !url.password &&
      (!url.port || url.port === "443") && Boolean(url.pathname.replaceAll("/", ""));
  } catch { return false; }
}

export function validateInstagramPatch(patch: Record<string, unknown>): { update?: Record<string, unknown>; error?: string } {
  const update: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(patch)) {
    if (Object.hasOwn(ENUMS, key)) {
      if (typeof value !== "string" || !ENUMS[key].includes(value)) return {error: `Unexpected value for ${key}.`};
      update[key] = value;
    } else if (BOOLEANS.has(key)) {
      if (typeof value !== "boolean") return {error: `Expected a switch value for ${key}.`};
      update[key] = value;
    } else if (key === "telegram_handle") {
      const handle = String(value ?? "").trim().replace(/^@+/, "");
      if (handle && !/^[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(handle)) return {error: "Use a Telegram username with 5–32 letters, digits or _."};
      update[key] = handle;
    } else if (key === "bio_link") {
      const url = String(value ?? "").trim();
      if (url && !validLinkPage(url)) return {error: "Use your HTTPS linkovne.com profile URL."};
      update[key] = url;
    } else return {error: `Unknown setting: ${key}`};
  }
  return {update};
}
