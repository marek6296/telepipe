import { NextResponse } from "next/server";
import { miniCookieOptions, miniError, miniRequestGuard, refreshMini } from "@/lib/telegram-mini-server";
import { MINI_COOKIE } from "@/lib/telegram-mini-policy";
const headers={"Cache-Control":"private, no-store"};
export async function POST(request:Request) {
  try {
    miniRequestGuard(request);
    const result=await refreshMini();
    const response=NextResponse.json({expiresAt:result.expiresAt},{headers});
    response.cookies.set(MINI_COOKIE,result.token,{...miniCookieOptions,expires:new Date(result.expiresAt),maxAge:Math.max(0,Math.floor((Date.parse(result.expiresAt)-Date.now())/1000))});
    return response;
  } catch(error) { const e=miniError(error); return NextResponse.json({error:e.message},{status:e.status,headers}); }
}
