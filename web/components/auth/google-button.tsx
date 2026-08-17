"use client";

import { useState, useTransition } from "react";

import { signInWithGoogleAction } from "@/app/(auth)/actions";
import { googleAuthEnabled } from "@/lib/flags";

/**
 * Google OAuth button. Flow je hotový (`signInWithGoogleAction`), ale kým Marek
 * nenastaví Google providera v Supabase, je button vypnutý za flagom
 * NEXT_PUBLIC_GOOGLE_AUTH s tooltipom „Available soon".
 */
export function GoogleButton({ label = "Continue with Google" }: { label?: string }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const disabled = !googleAuthEnabled || pending;

  const onGoogleSignIn = () => {
    if (!googleAuthEnabled) return;
    setError(null);
    startTransition(async () => {
      const result = await signInWithGoogleAction();
      if (result?.error) setError(result.error);
    });
  };

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onGoogleSignIn}
        disabled={disabled}
        aria-disabled={disabled}
        title={googleAuthEnabled ? undefined : "Available soon"}
        className="lp-btn lp-btn-ghost h-12 w-full text-[14px]"
      >
        <GoogleIcon />
        {label}
      </button>

      {/* Tooltip „Available soon" — len keď je flag vypnutý */}
      {!googleAuthEnabled && (
        <span
          role="tooltip"
          className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg border border-white/12 bg-[#101010] px-2.5 py-1.5 text-[11.5px] font-medium text-white/75 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100"
        >
          Available soon
        </span>
      )}

      {error && (
        <p role="alert" className="mt-2 text-[12px] text-[#f87171]">
          {error}
        </p>
      )}
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.63h6.46a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.58-5.17 3.58-8.8Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.08 7.94-2.93l-3.88-3c-1.08.72-2.45 1.15-4.06 1.15-3.12 0-5.77-2.11-6.71-4.95H1.28v3.09A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.29 14.27a7.2 7.2 0 0 1 0-4.54V6.64H1.28a12 12 0 0 0 0 10.72l4.01-3.09Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.76 0 3.34.61 4.59 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.28 6.64l4.01 3.09C6.23 6.86 8.88 4.75 12 4.75Z"
      />
    </svg>
  );
}
