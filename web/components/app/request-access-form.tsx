"use client";

import { useActionState } from "react";

import { requestAccessAction } from "@/app/locked/actions";

export function RequestAccessForm() {
  const [state, formAction, pending] = useActionState(requestAccessAction, undefined);

  if (state?.ok) {
    return (
      <p className="mt-5 text-[14px] text-[var(--app-text-2)]" role="status">
        Request sent — we&apos;ll be in touch shortly.
      </p>
    );
  }

  return (
    <form action={formAction} className="mt-5 space-y-3">
      <label htmlFor="message" className="block text-[12.5px] text-[var(--app-text-3)]">
        What do you want to run? (optional)
      </label>
      <textarea
        id="message"
        name="message"
        rows={3}
        maxLength={1000}
        className="app-input w-full resize-none"
        placeholder="One Telegram persona, maybe Fanvue later…"
      />
      {state?.error && (
        <p className="text-[13px] text-[#fca5a5]" role="alert">
          {state.error}
        </p>
      )}
      <button type="submit" disabled={pending} className="app-btn app-btn-primary">
        {pending ? "Sending…" : "Request access"}
      </button>
    </form>
  );
}
