import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthForm, AuthShell } from "@/components/auth-form";

export const metadata: Metadata = { title: "Sign in" };

export default function SignIn() {
  return (
    <AuthShell>
      <Suspense>
        <AuthForm mode="signin" />
      </Suspense>
    </AuthShell>
  );
}
