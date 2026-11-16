import type { Metadata } from "next";
import { SocialWorkspace } from "@/components/app/social/workspace";
import { requireModelTab } from "@/lib/models";
import { loadSocialSnapshot } from "@/lib/social-server";

export const metadata: Metadata = { title: "Social sites" };

export default async function SocialPage({ params }: PageProps<"/app/m/[id]/social">) {
  const { id } = await params;
  await requireModelTab(id, "social");
  const snapshot = await loadSocialSnapshot(id, {});
  return <SocialWorkspace initial={snapshot} />;
}
