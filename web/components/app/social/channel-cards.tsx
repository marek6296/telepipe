"use client";

import Link from "next/link";
import { useRef, useState, type ReactNode } from "react";
import { ArrowUpRight, Camera, ChevronDown, Heart, Loader2, Send } from "lucide-react";
import { useSocialTransport } from "./transport";
import type { SocialChannelState, SocialMode } from "@/lib/social-types";
import { cn } from "@/lib/utils";
import { CHANNEL_NAMES, sourceTime } from "./state";

const ICONS = { telegram: Send, instagram: Camera, fanvue: Heart };
const MODES: { value: SocialMode; label: string }[] = [{ value: "off", label: "Manual" }, { value: "semi", label: "Semi" }, { value: "auto", label: "Auto" }];

export function ChannelCards({ modelId, channels, refresh, headerActions }: { modelId: string; channels: SocialChannelState[]; refresh: () => void; headerActions?:ReactNode }) {
  const { mini } = useSocialTransport();
  return <>
    <div className={cn("relative",!mini && "sm:hidden")}><details className="app-card group">
      <summary className={cn("cursor-pointer list-none px-4 py-3.5 [&::-webkit-details-marker]:hidden",mini && "mini-channel-summary")}>
        <span className="flex items-center justify-between gap-3 text-[12px] font-medium"><span className="shrink-0">{mini ? "Channels & modes" : "Channels & reply modes"}</span>{mini && headerActions && <span className="mini-channel-status ml-auto">{headerActions}</span>}<ChevronDown className={cn("h-3.5 w-3.5 text-[var(--app-text-4)] transition-transform group-open:rotate-180",mini && "shrink-0")} /></span>
        <span className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-[var(--app-text-3)]">{channels.map(channel => <span key={channel.channel} className="inline-flex items-center gap-1.5"><span className={cn("h-1 w-1 rounded-full", channel.available && channel.connected ? "bg-[var(--app-up)]" : "bg-[var(--app-text-4)]")} />{CHANNEL_NAMES[channel.channel]} · {channel.available ? channel.connected ? MODES.find(mode => mode.value === channel.mode)?.label : "Offline" : "Unavailable"}</span>)}</span>
      </summary>
      <div className="grid gap-3 border-t border-[var(--app-border)] p-3">{channels.map(channel => <ChannelCard key={channel.channel} modelId={modelId} state={channel} refresh={refresh} />)}</div>
    </details></div>
    <div className={mini ? "hidden" : "hidden gap-3 sm:grid sm:grid-cols-3"}>{channels.map(channel => <ChannelCard key={channel.channel} modelId={modelId} state={channel} refresh={refresh} />)}</div>
  </>;
}

function ChannelCard({ modelId, state, refresh }: { modelId: string; state: SocialChannelState; refresh: () => void }) {
  const { transport: { setSocialMode }, mini } = useSocialTransport();
  const [saving, setSaving] = useState<SocialMode | null>(null);
  const [error, setError] = useState("");
  const busy = useRef(false);
  const Icon = ICONS[state.channel];
  async function save(mode: SocialMode) {
    if (busy.current || mode === state.mode) return;
    busy.current = true;
    setSaving(mode); setError("");
    try {
      const result = await setSocialMode(modelId, state.channel, mode);
      if (result.error) setError(result.error);
      else refresh();
    } catch { setError("Could not save the mode. Try again."); }
    finally { busy.current = false; setSaving(null); }
  }
  return <section className="app-card min-w-0 p-4" aria-label={`${CHANNEL_NAMES[state.channel]} connection and reply mode`}>
    <div className="flex items-start justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="rounded-lg border border-[var(--app-border)] p-2 text-[var(--app-text-2)]"><Icon className="h-4 w-4" strokeWidth={1.6} /></span>
        <div className="min-w-0"><h2 className="text-[13px] font-medium">{CHANNEL_NAMES[state.channel]}</h2><p className="truncate text-[11px] text-[var(--app-text-3)]">{state.available ? state.handle || (state.connected ? "Connected account" : "No account connected") : "Not available yet"}</p></div>
      </div>
      <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", state.connected && state.available ? "bg-[var(--app-up)]" : "bg-[var(--app-text-4)]")} title={state.connected ? "Connected" : "Disconnected"} />
    </div>
    <div className="mt-4 grid grid-cols-3 gap-1 rounded-lg border border-[var(--app-border)] bg-black/15 p-1" aria-label={`${CHANNEL_NAMES[state.channel]} reply mode`}>
      {MODES.map(mode => <button key={mode.value} type="button" aria-pressed={state.mode === mode.value} disabled={!state.available || !state.connected || saving !== null} onClick={() => void save(mode.value)} className={cn("flex min-h-8 items-center justify-center gap-1 rounded-md px-1 text-[11.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-45", state.mode === mode.value ? "bg-[var(--app-surface-hover)] font-medium text-[var(--app-text)] shadow-sm" : "text-[var(--app-text-3)] hover:text-[var(--app-text)]")}>
        {saving === mode.value && <Loader2 className="h-3 w-3 animate-spin" />}{mode.label}
      </button>)}
    </div>
    <p className="mt-2 min-h-8 text-[11px] leading-4 text-[var(--app-text-3)]">{state.notice || (state.mode === "off" ? "You write every reply. AI stays quiet." : state.mode === "semi" ? "AI drafts. You approve each reply." : "AI replies within her daily schedule.")}</p>
    {state.syncStatus && <p className="mt-1 truncate text-[10px] text-[var(--app-text-4)]" title={state.lastSyncAt ? `Last sync: ${sourceTime(state.lastSyncAt)}` : undefined}>History · {state.syncStatus.replaceAll("_", " ")}</p>}
    {error && <p role="alert" className="mt-2 text-[11px] text-[#fca5a5]">{error}</p>}
    {state.available && !mini && <div className="mt-3 flex items-center gap-3 border-t border-[var(--app-border)] pt-2.5 text-[11px] text-[var(--app-text-3)]">
      <Link href={state.connectHref} className="inline-flex items-center gap-1 hover:text-[var(--app-text)]">{state.connected ? "Connection" : "Connect account"}<ArrowUpRight className="h-3 w-3" /></Link>
      <Link href={state.settingsHref} className="hover:text-[var(--app-text)]">Settings</Link>
    </div>}
  </section>;
}
