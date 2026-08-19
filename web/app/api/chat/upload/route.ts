import { NextResponse, type NextRequest } from "next/server";

import { createClient, getUser } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

/**
 * Nahratie fotky do DM.
 *
 * Cesta je vždy `dm/<owner_account_id>/<uuid>.<ext>` — z nej si storage policy
 * odvodí, čia konverzácia to je. Upload ide USER-scoped klientom, takže
 * rozhoduje tá istá policy ako pri čítaní; service key sa tu neobjaví.
 */
export async function POST(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  const roomId = String(form?.get("roomId") ?? "");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file." }, { status: 400 });
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json({ error: "Image is larger than 10 MB." }, { status: 413 });
  }
  if (!ALLOWED.has(file.type)) {
    return NextResponse.json({ error: "Only JPEG, PNG, WebP or GIF." }, { status: 415 });
  }

  const supabase = await createClient();

  // Fotky sú len v DM. RLS na `chat_messages` to ustráži aj tak, ale nechceme
  // nahrať súbor, ktorý sa potom nedá k ničomu pripojiť.
  const { data: room } = await supabase
    .from("chat_rooms")
    .select("kind, owner_account_id")
    .eq("id", roomId)
    .maybeSingle();

  if (!room || room.kind !== "admin_dm" || !room.owner_account_id) {
    return NextResponse.json({ error: "Photos are only allowed in support chat." }, { status: 403 });
  }

  const ext = file.type.split("/")[1]?.replace("jpeg", "jpg") ?? "jpg";
  const path = `dm/${room.owner_account_id}/${crypto.randomUUID()}.${ext}`;

  const { error } = await supabase.storage
    .from("chat")
    .upload(path, file, { contentType: file.type, upsert: false });

  if (error) {
    console.error("chat upload failed:", error.message);
    return NextResponse.json({ error: "Upload failed." }, { status: 500 });
  }

  return NextResponse.json({ path });
}
