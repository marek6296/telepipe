"use client";

import Script from "next/script";
import { useRef, useCallback, useEffect, useState, type RefObject } from "react";
import { Loader2 } from "lucide-react";
import type { SocialSnapshot, SocialThread } from "@/lib/social-types";
import { SocialWorkspace, type SocialNavigation } from "./workspace";
import { SocialTransportProvider } from "./transport";
import { createMiniTransport, SESSION_EXPIRED } from "./transport-core";
import { telegramWebApp, useTelegramShell } from "./telegram-shell";
import { connectMiniSession, notificationTarget, type MiniSession as Session } from "./mini-session";

type MiniTransport = ReturnType<typeof createMiniTransport>;
// Strict-mode remounts share the bootstrap promise: signed initData is one use.
let initialSession:{key:string; promise:Promise<Session>}|undefined;


export function MiniApp() {
  const [sdkReady,setSdkReady] = useState(false);
  const [attempt,setAttempt] = useState(0);
  const [transport,setTransport] = useState<MiniTransport|null>(null);
  const [error,setError] = useState("");
  const [expired,setExpired] = useState(false);
  const [workspace,setWorkspace] = useState<{id:string;contact:string|null}|null>(null);
  const [chatOpen,setChatOpen] = useState(false);
  const navigation = useRef<SocialNavigation|null>(null);
  const selectionChanged = useCallback((key:string|null) => setChatOpen(Boolean(key)),[]);

  useEffect(() => {
    if (!sdkReady) return;
    let alive = true;
    const params = new URLSearchParams(window.location.search);

    const bot = params.get("bot");
    const initData = telegramWebApp()?.initData;
    const key = `${bot}\0${initData || ""}`;
    if (!initialSession || initialSession.key !== key) {
      initialSession = {key,promise:connectMiniSession({bot,initData}).catch(error => { if (initialSession?.key === key) initialSession = undefined; throw error; })};
    }
    initialSession.promise.then(result => {
      if (!alive) return;
      if (!bot || result.selectedModelId !== bot || !result.models.some(model=>model.id===bot)) throw new Error("This bot's model is not available.");
      const target = notificationTarget(result,bot,params.get("contact"),bot);
      setWorkspace({id:bot,contact:target?.contact ?? null});
      setChatOpen(Boolean(target));
      setTransport(createMiniTransport({token:result.token,onExpired:() => setExpired(true)}));
    }).catch(error => { if (alive) setError(error instanceof Error ? error.message : "Could not connect. Try again."); });
    return () => { alive = false; };
  },[sdkReady,attempt]);

  useEffect(() => {
    if (!transport || expired) return;
    let refreshing = false;
    const refresh = async () => {
      if (document.visibilityState !== "visible" || refreshing) return;
      refreshing = true;
      try { await transport.refresh(); } catch { /* 401 is terminal; network errors retry on the next foreground. */ }
      finally { refreshing = false; }
    };
    const timer = window.setInterval(() => void refresh(),10 * 60 * 1000);
    const app = telegramWebApp();
    app?.onEvent("activated",refresh);
    window.addEventListener("focus",refresh);
    document.addEventListener("visibilitychange",refresh);
    return () => { window.clearInterval(timer); app?.offEvent("activated",refresh); window.removeEventListener("focus",refresh); document.removeEventListener("visibilitychange",refresh); };
  },[transport,expired]);

  const back = useCallback(() => { navigation.current?.back(); },[]);
  useTelegramShell(sdkReady,chatOpen ? back : null);

  return <main id="mini-shell" className="mini-shell app-scope" data-theme="dark">
    <Script src="https://telegram.org/js/telegram-web-app.js" strategy="afterInteractive" onReady={() => setSdkReady(true)} onError={() => setSdkReady(true)} />
    {expired ? <div role="alert" className="mini-state"><h2 className="text-[18px] font-medium">Reopen Social sites</h2><p className="mt-3 text-[13px] leading-6 text-[var(--app-text-3)]">{SESSION_EXPIRED}</p></div>
      : !transport ? <div className="mini-state">{error ? <><h2 className="text-[18px] font-medium">Connect through Telegram</h2><p role="alert" className="mt-3 text-[13px] leading-6 text-[var(--app-text-3)]">{error}</p><button type="button" onClick={() => { setError(""); setAttempt(value => value + 1); }} className="app-btn app-btn-ghost mt-5 min-h-11 px-5">Try again</button></> : <p role="status" className="flex items-center justify-center gap-2 text-[13px] text-[var(--app-text-3)]"><Loader2 className="h-4 w-4 animate-spin" />Connecting securely…</p>}</div> : <>
      {workspace && <div className="mini-model-workspace"><SocialTransportProvider transport={transport} active><ModelWorkspace modelId={workspace.id} transport={transport} contact={workspace.contact} navigationRef={navigation} onSelectionChange={selectionChanged} /></SocialTransportProvider></div>}
    </>}
  </main>;
}

function ModelWorkspace({modelId,transport,contact,navigationRef,onSelectionChange}: {modelId:string; transport:MiniTransport; contact:string|null; navigationRef:RefObject<SocialNavigation|null>; onSelectionChange:(key:string|null)=>void}) {
  const [loaded,setLoaded] = useState<{snapshot:SocialSnapshot;thread:SocialThread|null;selectionError:string|null}|null>(null);
  const [error,setError] = useState("");
  const [attempt,setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const colon = contact?.indexOf(":") ?? -1;
    const threadURL = contact && colon > 0 ? `/api/models/${modelId}/social/thread?${new URLSearchParams({channel:contact.slice(0,colon),externalId:contact.slice(colon + 1)})}` : null;
    void Promise.allSettled([
      transport.read<SocialSnapshot>(`/api/models/${modelId}/social`,controller.signal),
      threadURL ? transport.read<SocialThread>(threadURL,controller.signal) : Promise.resolve(null),
    ]).then(([snapshot,thread]) => {
      if (controller.signal.aborted) return;
      if (snapshot.status === "rejected") { setError(snapshot.reason instanceof Error ? snapshot.reason.message : "Could not load this inbox."); return; }
      setLoaded({snapshot:snapshot.value,thread:thread.status === "fulfilled" ? thread.value : null,selectionError:thread.status === "rejected" ? "The linked conversation could not be opened." : null});
    });
    return () => controller.abort();
  },[modelId,transport,contact,attempt]);
  if (!loaded) return <div className="mini-state">{error ? <><p role="alert" className="text-[13px] leading-6">{error}</p><button type="button" onClick={() => { setError(""); setAttempt(value => value + 1); }} className="app-btn app-btn-ghost mt-4 min-h-11 px-5">Retry inbox</button></> : <p role="status" className="flex justify-center gap-2 text-[13px] text-[var(--app-text-3)]"><Loader2 className="h-4 w-4 animate-spin" />Loading conversations…</p>}</div>;
  return <SocialWorkspace initial={loaded.snapshot} initialThread={loaded.thread} selectionError={loaded.selectionError} navigationRef={navigationRef} onSelectionChange={onSelectionChange} />;
}
