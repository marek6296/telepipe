import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { SignUpForm } from "@/components/auth/sign-up-form";

export const metadata: Metadata = {
  title: "Create account",
  description: "Create your Telepipe account and put your DMs on autopilot.",
};

export default function RegisterPage() {
  return (
    <AuthShell>
      <SignUpForm />
    </AuthShell>
  );
}
