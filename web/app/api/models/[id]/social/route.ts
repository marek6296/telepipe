import { NextRequest, NextResponse } from "next/server";
import { loadSocialSnapshot, socialErrorMessage } from "@/lib/social-server";
import { parseSocialQuery, SocialError } from "@/lib/social-policy";

export async function GET(request: NextRequest, {params}: {params: Promise<{id:string}>}) {
  try {
    const {id} = await params;
    return NextResponse.json(await loadSocialSnapshot(id,parseSocialQuery(request.nextUrl.searchParams)),{headers:{"Cache-Control":"private, no-store"}});
  } catch (error) {
    return NextResponse.json({error:socialErrorMessage(error)},{status:error instanceof SocialError ? error.status : 500,headers:{"Cache-Control":"private, no-store"}});
  }
}
