import { NextResponse } from "next/server";
import { linkSocialContacts, setSocialMode, setSocialTakeover, skipSocialPending, submitSocialCommand, unlinkSocialContact } from "@/app/app/m/[id]/social/actions";
import { miniError, miniJson, miniRequestGuard, miniSession } from "@/lib/telegram-mini-server";
import { MiniAuthError } from "@/lib/telegram-mini-policy";
import type { SocialChannel, SocialCommandInput, SocialMode } from "@/lib/social-types";
import { UUID } from "@/lib/social-policy";
const headers={"Cache-Control":"private, no-store"};
export async function POST(request:Request) {
  try {
    miniRequestGuard(request);
    if (!request.headers.has("authorization") && request.headers.get("x-telepipe-mini")!=="1") throw new MiniAuthError();
    await miniSession(); // This route never falls back to the ordinary web login.
    const body=await miniJson(request);
    if (typeof body.modelId!=="string" || !UUID.test(body.modelId)) throw new MiniAuthError("Invalid model.",400);
    const modelId=body.modelId;
    let result;
    switch (body.action) {
      case "command": result=await submitSocialCommand(modelId,body.input as SocialCommandInput); break;
      case "mode": result=await setSocialMode(modelId,body.channel as SocialChannel,body.mode as SocialMode); break;
      case "takeover": result=await setSocialTakeover(modelId,body.contactKey as string,body.takeover as boolean); break;
      case "link": result=await linkSocialContacts(modelId,body.firstKey as string,body.secondKey as string); break;
      case "unlink": result=await unlinkSocialContact(modelId,body.contactKey as string); break;
      case "skip": result=await skipSocialPending(modelId,body.pendingId as string,body.expectedSuggestions as string[]); break;
      default: throw new MiniAuthError("Unknown action.",400);
    }
    return NextResponse.json(result,{headers});
  } catch(error) { const e=miniError(error); return NextResponse.json({error:e.message},{status:e.status,headers}); }
}
