import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthForm, AuthShell } from "@/components/auth-form";

export const metadata: Metadata = { title: "Create your account" };

export default function SignUp() {
  return (
    <AuthShell>
      <Suspense>
        <AuthForm mode="signup" />
      </Suspense>
    </AuthShell>
  );
}
