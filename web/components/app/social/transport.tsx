"use client";

import { createContext, useContext, type ReactNode } from "react";
import * as actions from "@/app/app/m/[id]/social/actions";
import type { SocialTransport } from "./transport-core";

const webTransport: SocialTransport = {
  ...actions,
  async read<T>(url: string, signal?: AbortSignal): Promise<T> {
    const response = await fetch(url,{signal,cache:"no-store",credentials:"same-origin"});
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.error === "string" ? body.error : "Could not refresh. Try again.");
    return body as T;
  },
};
const Context = createContext({transport:webTransport,active:true,mini:false});
export function SocialTransportProvider({transport, active = true, children}: {transport:SocialTransport; active?:boolean; children:ReactNode}) {
  return <Context.Provider value={{transport,active,mini:true}}>{children}</Context.Provider>;
}
export function useSocialTransport() { return useContext(Context); }
