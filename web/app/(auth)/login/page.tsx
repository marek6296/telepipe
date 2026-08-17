import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { SignInForm } from "@/components/auth/sign-in-form";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to your Telepipe account.",
};

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const params = await searchParams;
  const raw = params?.next;
  const next = typeof raw === "string" ? raw : undefined;

  return (
    <AuthShell>
      <SignInForm next={next} />
    </AuthShell>
  );
}
