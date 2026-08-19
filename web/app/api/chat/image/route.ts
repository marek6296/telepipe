import { NextResponse, type NextRequest } from "next/server";

import { createClient, getUser } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/**
 * Fotka z DM. Bucket `chat` je privátny, takže sa nedá dať priamo do `src`
 * — táto route vyrobí krátko platnú signed URL a presmeruje na ňu. Vďaka tomu
 * môže komponent písať `<img src="/api/chat/image?path=…">` a o podpisovaní
 * nevedieť.
 *
 * Podpis vyrába USER-scoped klient, takže storage policy `chat_read` rozhodne,
 * či ju vôbec dostane: cudziu konverzáciu si nikto nepodpíše.
 */
export async function GET(request: NextRequest) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const path = request.nextUrl.searchParams.get("path") ?? "";
  // Cesta chodí z databázy, ale kontrola tvaru je lacná a zabráni pokusom
  // o vyskočenie z bucketu.
  if (!/^dm\/[0-9a-f-]{36}\/[0-9a-f-]{36}\.(jpg|png|webp|gif)$/.test(path)) {
    return NextResponse.json({ error: "Bad path." }, { status: 400 });
  }

  const supabase = await createClient();
  const { data, error } = await supabase.storage.from("chat").createSignedUrl(path, 300);

  if (error || !data) {
    return NextResponse.json({ error: "Not found." }, { status: 404 });
  }
  return NextResponse.redirect(data.signedUrl);
}
