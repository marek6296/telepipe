import { NextRequest, NextResponse } from "next/server";
import { loadSocialThread, socialErrorMessage } from "@/lib/social-server";
import { SocialError } from "@/lib/social-policy";

export async function GET(request: NextRequest, {params}: {params: Promise<{id:string}>}) {
  try {
    const {id} = await params;
    const query = request.nextUrl.searchParams;
    return NextResponse.json(await loadSocialThread(id,`${query.get("channel") || ""}:${query.get("externalId") || ""}`,query.get("before") || undefined),{headers:{"Cache-Control":"private, no-store"}});
  } catch (error) {
    return NextResponse.json({error:socialErrorMessage(error)},{status:error instanceof SocialError ? error.status : 500,headers:{"Cache-Control":"private, no-store"}});
  }
}
