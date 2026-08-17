/**
 * Feature flagy bezpečné pre client bundle — samostatný modul, aby si client
 * komponenty nemuseli ťahať `lib/env.ts` (kde žijú aj server-only kľúče).
 */

/** Google OAuth je pripravený v kóde, ale vypnutý kým Marek nenastaví provider. */
export const googleAuthEnabled = process.env.NEXT_PUBLIC_GOOGLE_AUTH === "true";
