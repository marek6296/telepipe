import * as React from "react";

import { cn } from "@/lib/utils";

/** Glass input zo SignInPage predlohy — blur podklad, zlatý focus ring. */
export function Input({
  className,
  type = "text",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input type={type} className={cn("glass-input", className)} {...props} />;
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea className={cn("glass-input resize-y min-h-28", className)} {...props} />
  );
}

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "block text-sm font-medium text-white/70 mb-2 tracking-tight",
        className,
      )}
      {...props}
    />
  );
}
