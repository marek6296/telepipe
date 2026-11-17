import { NextResponse } from "next/server";
import { miniError, miniModels } from "@/lib/telegram-mini-server";
const headers={"Cache-Control":"private, no-store"};
export async function GET(request:Request) {
  try { return NextResponse.json(await miniModels(new URL(request.url).searchParams.get("bot")),{headers}); }
  catch(error) { const e=miniError(error); return NextResponse.json({error:e.message},{status:e.status,headers}); }
}
