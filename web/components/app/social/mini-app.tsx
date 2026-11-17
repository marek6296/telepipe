"use client";

import Script from "next/script";
import { createRef, useCallback, useEffect, useState, type RefObject } from "react";
import { ArrowLeft, ArrowRight, ChevronDown, Loader2, MessageSquare } from "lucide-react";
import type { SocialSnapshot, SocialThread } from "@/lib/social-types";
import { SocialWorkspace, type SocialNavigation } from "./workspace";
import { SocialTransportProvider } from "./transport";
import { createMiniTransport, SESSION_EXPIRED } from "./transport-core";
import { telegramWebApp, useTelegramShell } from "./telegram-shell";
import { connectMiniSession, notificationTarget, type MiniModel as Model, type MiniSession as Session } from "./mini-session";

type MiniTransport = ReturnType<typeof createMiniTransport>;
// Strict-mode remounts share the bootstrap promise: signed initData is one use.
let initialSession:{key:string; promise:Promise<Session>}|undefined;


export function MiniApp() {
  const [sdkReady,setSdkReady] = useState(false);
  const [attempt,setAttempt] = useState(0);
  const [session,setSession] = useState<Session|null>(null);
  const [transport,setTransport] = useState<MiniTransport|null>(null);
  const [error,setError] = useState("");
  const [expired,setExpired] = useState(false);
  const [selected,setSelected] = useState<string|null>(null);
  const [visited,setVisited] = useState<{id:string;contact:string|null;navigation:RefObject<SocialNavigation|null>}[]>([]);
  const [lastModel,setLastModel] = useState<string|null>(null);
  const [launch,setLaunch] = useState<{bot:string|null;contact:string|null}|null>(null);

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
      const target = notificationTarget(result,bot,params.get("contact"));
      setLaunch({bot,contact:target?.contact ?? null});
      if (target) {
        setVisited([{...target,navigation:createRef<SocialNavigation>()}]);
        setSelected(target.id);
      }
      try { setLastModel(localStorage.getItem("telepipe-mini-model")); } catch { /* Storage is optional in embedded browsers. */ }
      setSession(result);
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

  const back = useCallback(() => {
    if (selected && visited.find(item => item.id === selected)?.navigation.current?.back()) return;
    setSelected(null);
  },[selected,visited]);
  useTelegramShell(sdkReady,selected ? back : null);

  function choose(model:Model) {
    setVisited(previous => previous.some(item => item.id === model.id) ? previous : [...previous,{id:model.id,contact:launch?.bot === model.id ? launch.contact : null,navigation:createRef<SocialNavigation>()}]);
    setSelected(model.id);
    setLastModel(model.id);
    try { localStorage.setItem("telepipe-mini-model",model.id); } catch { /* No auth data is persisted. */ }
    const url = new URL(window.location.href);
    url.searchParams.set("model",model.id);
    const currentKey = visited.find(item => item.id === model.id)?.navigation.current?.contactKey();
    const contact = currentKey === undefined && model.id === launch?.bot ? launch.contact : currentKey;
    if (contact) url.searchParams.set("contact",contact);
    else url.searchParams.delete("contact");
    window.history.replaceState(window.history.state,"",`${url.pathname}${url.search}`);
  }
  const models = [...(session?.models || [])].sort((a,b) => Number(b.id === lastModel) - Number(a.id === lastModel));
  const currentModel = session?.models.find(model => model.id === selected);
  return <main id="mini-shell" className="mini-shell app-scope" data-theme="dark">
    <Script src="https://telegram.org/js/telegram-web-app.js" strategy="afterInteractive" onReady={() => setSdkReady(true)} onError={() => setSdkReady(true)} />
    <header className="mini-header">
      {selected ? <button type="button" onClick={back} aria-label="Back" className="app-btn app-btn-quiet h-11 w-11 shrink-0"><ArrowLeft className="h-4 w-4" /></button> : <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--app-border-strong)]"><MessageSquare className="h-4 w-4" /></span>}
      <div className="min-w-0 flex-1"><p className="text-[10px] uppercase tracking-[0.16em] text-[var(--app-text-3)]">Telepipe</p><h1 className="truncate text-[15px] font-medium">{currentModel?.name || "Social sites"}</h1></div>
      {selected && <button type="button" onClick={() => setSelected(null)} className="app-btn app-btn-ghost min-h-10 gap-1 px-3 text-[11px]">Models<ChevronDown className="h-3 w-3" /></button>}
    </header>
    {expired ? <div role="alert" className="mini-state"><h2 className="text-[18px] font-medium">Reopen Social sites</h2><p className="mt-3 text-[13px] leading-6 text-[var(--app-text-3)]">{SESSION_EXPIRED}</p></div>
      : !transport ? <div className="mini-state">{error ? <><h2 className="text-[18px] font-medium">Connect through Telegram</h2><p role="alert" className="mt-3 text-[13px] leading-6 text-[var(--app-text-3)]">{error}</p><button type="button" onClick={() => { setError(""); setAttempt(value => value + 1); }} className="app-btn app-btn-ghost mt-5 min-h-11 px-5">Try again</button></> : <p role="status" className="flex items-center justify-center gap-2 text-[13px] text-[var(--app-text-3)]"><Loader2 className="h-4 w-4 animate-spin" />Connecting securely…</p>}</div> : <>
      {!selected && <div className="mini-model-picker"><h2 className="text-[23px] font-medium tracking-tight">Choose a model</h2><p className="mt-2 text-[13px] leading-6 text-[var(--app-text-3)]">Her conversations, reply modes and drafts in one place.</p><ul className="mt-7 space-y-3">{models.map(model => <li key={model.id}><button type="button" onClick={() => choose(model)} className="app-card flex min-h-20 w-full items-center gap-3 p-4 text-left hover:bg-[var(--app-surface-hover)]"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[17px]">{model.name.slice(0,1).toUpperCase()}</span><span className="min-w-0 flex-1"><span className="block truncate text-[14px] font-medium">{model.name}</span><span className="mt-1 block text-[11px] text-[var(--app-text-3)]">{model.id === lastModel ? "Last opened" : "Open inbox"}</span></span><ArrowRight className="h-4 w-4 text-[var(--app-text-3)]" /></button></li>)}</ul>{models.length === 0 && <p className="app-card mt-6 p-5 text-[13px] text-[var(--app-text-3)]">No models are available for this paired account.</p>}<p className="mt-7 text-[10px] leading-5 text-[var(--app-text-4)]">Only you can manage these conversations. Opening a chat does not mark messages as seen.</p></div>}
      {visited.map(item => <div key={item.id} className="mini-model-workspace" hidden={selected !== item.id}><SocialTransportProvider transport={transport} active={selected === item.id}><ModelWorkspace modelId={item.id} transport={transport} contact={item.contact} navigationRef={item.navigation} /></SocialTransportProvider></div>)}
    </>}
  </main>;
}

function ModelWorkspace({modelId,transport,contact,navigationRef}: {modelId:string; transport:MiniTransport; contact:string|null; navigationRef:RefObject<SocialNavigation|null>}) {
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
  return <SocialWorkspace initial={loaded.snapshot} initialThread={loaded.thread} selectionError={loaded.selectionError} navigationRef={navigationRef} />;
}
