import type { Metadata } from "next";
import { SocialWorkspace } from "@/components/app/social/workspace";
import { requireModelTab } from "@/lib/models";
import { loadSocialSelection, loadSocialSnapshot } from "@/lib/social-server";

export const maxDuration=300;
export const metadata: Metadata = { title: "Social sites" };

export default async function SocialPage({ params, searchParams }: PageProps<"/app/m/[id]/social">) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  await requireModelTab(id, "social");
  const [snapshot, selection] = await Promise.all([
    loadSocialSnapshot(id, {}), loadSocialSelection(id, query.contact),
  ]);
  return <SocialWorkspace initial={snapshot} initialThread={selection.thread} selectionError={selection.error} />;
}
