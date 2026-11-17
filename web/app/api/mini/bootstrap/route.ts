import { NextResponse } from "next/server";
import { bootstrapMini, miniCookieOptions, miniError, miniJson, miniRequestGuard } from "@/lib/telegram-mini-server";
import { MINI_COOKIE } from "@/lib/telegram-mini-policy";
const headers={"Cache-Control":"private, no-store"};
export async function POST(request:Request) {
  try {
    miniRequestGuard(request);
    const body=await miniJson(request);
    const result=await bootstrapMini(body.bot,body.initData);
    const response=NextResponse.json(result,{headers});
    response.cookies.set(MINI_COOKIE,result.token,{...miniCookieOptions,expires:new Date(result.expiresAt)});
    return response;
  } catch(error) { const e=miniError(error); return NextResponse.json({error:e.message},{status:e.status,headers}); }
}
