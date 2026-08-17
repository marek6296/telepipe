import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { RequestResetForm } from "@/components/auth/reset-password-form";

export const metadata: Metadata = {
  title: "Reset password",
  description: "Request a password reset link for your Telepipe account.",
};

export default function ResetPasswordPage() {
  return (
    <AuthShell>
      <RequestResetForm />
    </AuthShell>
  );
}
