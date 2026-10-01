import type { Metadata } from "next";
import { AccountProvider } from "@/components/account";
import { Shell } from "@/components/shell";
import { Survey } from "@/components/survey";

export const metadata: Metadata = { title: "Dashboard", robots: { index: false } };

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AccountProvider>
      <Shell>{children}</Shell>
      <Survey />
    </AccountProvider>
  );
}
