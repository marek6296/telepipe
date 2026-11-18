"use client";

import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { ArrowLeft, ChevronLeft, ChevronRight, Inbox, Loader2, RefreshCw, Search } from "lucide-react";
import type { SocialChannel, SocialCommandInput, SocialContact, SocialFilter, SocialPerson, SocialSnapshot, SocialThread } from "@/lib/social-types";
import { cn } from "@/lib/utils";
import { ChannelCards } from "./channel-cards";
import { Conversation } from "./conversation";
import { CHANNEL_NAMES, sourceTime, waitingChannels, personChannelView, waitingMessageCount, replyInProgress } from "./state";
import { useSocialResource } from "./use-resource";
import { useSocialTransport } from "./transport";

export type ComposerDraft = {
  text: string; brief: string; submitting: boolean; error: string; notice: string;
  retry: SocialCommandInput | null;
  activity?: {input: SocialCommandInput; command?: import("@/lib/social-types").SocialCommand} | null;
};
export const EMPTY_DRAFT: ComposerDraft = { text: "", brief: "", submitting: false, error: "", notice: "", retry: null };
export type UpdateDraft = (key: string, change: (previous: ComposerDraft) => ComposerDraft) => void;
const FILTERS: { value: SocialFilter; label: string }[] = [
  { value: "all", label: "All" }, { value: "needs_reply", label: "Needs reply" }, { value: "approvals", label: "Approvals" }, { value: "manual", label: "Manual" },
];

export type SocialNavigation = { back: () => boolean; contactKey: () => string | null };
export function SocialWorkspace({ initial, initialThread = null, selectionError = null, navigationRef, onSelectionChange }: { initial: SocialSnapshot; initialThread?: SocialThread | null; selectionError?: string | null; navigationRef?: Ref<SocialNavigation>; onSelectionChange?:(key:string|null)=>void }) {
  const { mini } = useSocialTransport();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState({ search: "", channel: "all" as SocialChannel | "all", filter: "all" as SocialFilter, offset: 0 });
  const [selected, setSelected] = useState<SocialContact | null>(initialThread?.contact ?? null);
  useEffect(() => { onSelectionChange?.(selected?.key ?? null); },[selected?.key,onSelectionChange]);
  const entryKey = `${initialThread?.contact.key ?? ""}|${selectionError ?? ""}`;
  const [previousEntryKey, setPreviousEntryKey] = useState(entryKey);
  const [selectionDismissed, setSelectionDismissed] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, ComposerDraft>>({});
  const conversationRef = useRef<HTMLDivElement>(null);
  const updateDraft = useCallback<UpdateDraft>((key, change) => {
    setDrafts(previous => ({ ...previous, [key]: change(previous[key] ?? EMPTY_DRAFT) }));
  }, []);
  // A new server navigation may target another notification on this same page.
  // Adjust the selection without discarding the per-contact local draft map.
  if (previousEntryKey !== entryKey) {
    setPreviousEntryKey(entryKey);
    setSelected(initialThread?.contact ?? null);
    setSelectionDismissed(false);
  }

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(previous => previous.search === search.trim() ? previous : { ...previous, search: search.trim(), offset: 0 }), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const params = new URLSearchParams({ search: query.search, channel: query.channel, filter: query.filter, offset: String(query.offset) });
  const { data, error, loading, refresh } = useSocialResource<SocialSnapshot>(`/api/models/${initial.modelId}/social?${params}`, initial);
  const snapshot = data ?? initial;
  const activeChannels = snapshot.channels.filter(channel => channel.available);
  const people = data?.people ?? [];
  const total = data?.total ?? 0;
  const pageSize = data?.pageSize ?? initial.pageSize;
  const chooseContact = useCallback((contact: SocialContact | null) => {
    setSelected(contact);
    setSelectionDismissed(true);
    const url = new URL(window.location.href);
    if (contact) url.searchParams.set("contact", contact.key);
    else url.searchParams.delete("contact");
    // Keep the selected chat shareable without restarting readers or losing drafts.
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);
  useImperativeHandle(navigationRef, () => ({ contactKey: () => selected?.key ?? null, back: () => { if (!selected) return false; chooseContact(null); return true; } }), [selected, chooseContact]);
  function openPerson(contact: SocialContact) {
    chooseContact(contact);
    if (!mini && window.matchMedia("(max-width: 1023px)").matches) requestAnimationFrame(() => conversationRef.current?.scrollIntoView({ block: "start", behavior: "instant" }));
  }

  const workerStatus = (<span className="flex items-center gap-2 text-[11px] text-[var(--app-text-3)]">
        <span className={cn("h-1.5 w-1.5 rounded-full", snapshot.agent.running && !snapshot.agent.paused ? "bg-[var(--app-up)]" : "bg-[var(--app-text-4)]")} />
        <span>{snapshot.agent.paused ? "Replies paused" : snapshot.agent.running ? "Worker online" : "Worker offline"}</span>
        <button type="button" onClick={event => { event.preventDefault(); event.stopPropagation(); void refresh(); }} disabled={loading} aria-label="Refresh inbox" title="Refresh inbox" className="app-btn app-btn-quiet h-8 w-8"><RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /></button>
      </span>);

  return <div className={cn("social-workspace space-y-5", mini && selected && "mini-chat-open")}>
    {!mini && <div className="social-workspace-heading flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-[20px] font-semibold tracking-[-0.02em]">Social sites</h1><p className="mt-1 text-[12px] text-[var(--app-text-3)]">One inbox. The same person across her channels.</p></div>
      {workerStatus}
    </div>}
    <div className="social-channels"><ChannelCards modelId={initial.modelId} channels={snapshot.channels} refresh={refresh} headerActions={mini ? workerStatus : undefined} /></div>
    <div className="social-workspace-schedule flex flex-wrap justify-between gap-2 text-[10.5px] text-[var(--app-text-4)]">
      <span>{snapshot.agent.schedule} · {snapshot.agent.timezone}</span>
      <span>Refreshes every 5s while this page is visible</span>
    </div>
    {error && <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-[#fca5a5]/25 bg-[#fca5a5]/5 px-4 py-3 text-[12px] text-[#fca5a5]"><span>{error} {data ? "Showing the last saved view." : ""}</span><button type="button" onClick={() => void refresh()} className="shrink-0 underline underline-offset-2">Retry</button></div>}
    {selectionError && !selectionDismissed && <div role="alert" className="rounded-lg border border-[#fca5a5]/25 px-4 py-3 text-[12px] text-[#fca5a5]">{selectionError} Choose a conversation from the inbox.</div>}
    <div className="social-workspace-columns grid items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <section className={cn("social-inbox app-card min-w-0 overflow-hidden", selected && "hidden lg:block")} aria-label="People inbox">
        <div className="border-b border-[var(--app-border)] p-3.5">
          {!mini && <div className="mb-3 flex items-center justify-between"><h2 className="text-[13px] font-medium">People <span className="ml-1 text-[11px] font-normal text-[var(--app-text-4)]">{data ? total : "…"}</span></h2>{loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--app-text-4)]" aria-label="Refreshing people" />}</div>}
          <label className="relative block"><Search className="pointer-events-none absolute left-3 top-3 h-3.5 w-3.5 text-[var(--app-text-4)]" /><input aria-label="Search people" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search name or username" className="app-input h-9! pl-9! text-[12px]!" /></label>
          <div className={cn("mt-3 grid gap-1",mini ? "mini-inbox-filters grid-cols-4" : "grid-cols-2")} aria-label="Inbox filters">{FILTERS.map(filter => <button key={filter.value} type="button" aria-pressed={query.filter === filter.value} onClick={() => setQuery(previous => ({ ...previous, filter: filter.value, offset: 0 }))} className={cn("rounded-md px-2 py-1.5 text-left text-[11px] transition-colors", query.filter === filter.value ? "bg-[var(--app-surface-hover)] font-medium text-[var(--app-text)]" : "text-[var(--app-text-3)] hover:text-[var(--app-text)]")}>{filter.label}</button>)}</div>
          {mini ? <div className="mini-channel-filters" role="group" aria-label="Filter by channel">
            {(["all", "instagram", "fanvue", "telegram"] as const).map(channel => <button key={channel} type="button"
              aria-label={channel === "all" ? "All channels" : CHANNEL_NAMES[channel]} title={channel === "all" ? "All channels" : CHANNEL_NAMES[channel]}
              aria-pressed={query.channel === channel} data-channel={channel}
              onClick={() => setQuery(previous => ({...previous,channel,offset:0}))}>
              {channel === "all" ? "All" : <span aria-hidden="true" className="mini-channel-icon" style={{maskImage:`url(/social/${channel}.svg)`,WebkitMaskImage:`url(/social/${channel}.svg)`}} />}
            </button>)}
          </div> : <select aria-label="Filter by channel" value={query.channel} onChange={event => setQuery(previous => ({ ...previous, channel: event.target.value as SocialChannel | "all", offset: 0 }))} className="app-input mt-3 h-8! py-1! text-[11px]!"><option value="all">All channels</option>{activeChannels.map(channel => <option key={channel.channel} value={channel.channel}>{CHANNEL_NAMES[channel.channel]}</option>)}</select>}
        </div>
        {!data && loading ? <InboxSkeleton /> : people.length === 0 ? <div className="px-5 py-12 text-center"><Inbox className="mx-auto h-6 w-6 text-[var(--app-text-4)]" /><p className="mt-3 text-[13px]">{search || query.filter !== "all" ? "No matching conversations" : "No conversations yet"}</p><p className="mt-2 text-[11px] leading-5 text-[var(--app-text-3)]">{search || query.filter !== "all" ? "Try another name or filter." : "Connect a channel to bring your conversations here."}</p></div> : <ul className="max-h-[640px] divide-y divide-[var(--app-border)] overflow-y-auto">{people.map(person => <PersonRow key={person.id} person={person} drafts={drafts} loadedAt={snapshot.loadedAt} channel={query.channel} selected={selected?.key ?? null} select={openPerson} />)}</ul>}
        {total > pageSize && <div className="flex items-center justify-between border-t border-[var(--app-border)] px-3.5 py-2.5 text-[10.5px] text-[var(--app-text-3)]"><span>{query.offset + 1}–{Math.min(query.offset + pageSize, total)} of {total}</span><div className="flex gap-1"><button type="button" aria-label="Previous people" disabled={query.offset === 0 || loading} onClick={() => setQuery(previous => ({ ...previous, offset: Math.max(0, previous.offset - pageSize) }))} className="app-btn app-btn-quiet h-8 w-8"><ChevronLeft className="h-4 w-4" /></button><button type="button" aria-label="Next people" disabled={query.offset + pageSize >= total || loading} onClick={() => setQuery(previous => ({ ...previous, offset: previous.offset + pageSize }))} className="app-btn app-btn-quiet h-8 w-8"><ChevronRight className="h-4 w-4" /></button></div></div>}
      </section>
      <div ref={conversationRef} className={cn("social-conversation-column min-w-0 scroll-mt-20", !selected && "hidden lg:block")}>
        {selected ? <><button type="button" onClick={() => chooseContact(null)} className="social-back-people mb-3 inline-flex items-center gap-1.5 text-[12px] text-[var(--app-text-3)] lg:hidden"><ArrowLeft className="h-3.5 w-3.5" />All people</button><Conversation key={selected.key} modelId={initial.modelId} contact={selected} channelState={snapshot.channels.find(channel => channel.channel === selected.channel)} draft={drafts[selected.key] ?? EMPTY_DRAFT} updateDraft={updateDraft} initialThread={initialThread?.contact.key === selected.key ? initialThread : undefined} selectContact={chooseContact} refreshInbox={refresh} /></> : <div className="app-card flex min-h-[490px] items-center justify-center p-8 text-center"><div className="max-w-xs"><Inbox className="mx-auto h-8 w-8 text-[var(--app-text-4)]" strokeWidth={1.2} /><h2 className="mt-5 text-[16px] font-medium">Your conversations, together</h2><p className="mt-2 text-[12px] leading-6 text-[var(--app-text-3)]">Choose a person to see their messages, review suggestions and reply on the right channel.</p><p className="mt-5 text-[10.5px] text-[var(--app-text-4)]">Opening a chat does not mark messages as seen.</p></div></div>}
      </div>
    </div>
  </div>;
}

function PersonRow({ person, drafts, loadedAt, channel, selected, select }: { person: SocialPerson; drafts:Record<string,ComposerDraft>; loadedAt:string; channel:SocialChannel|"all"; selected: string | null; select: (contact: SocialContact) => void }) {
  const { mini } = useSocialTransport();
  const active = person.contacts.some(contact => contact.key === selected);
  const waiting = waitingChannels(person.contacts);
  const view = personChannelView(person,channel);
  const messageCount = waitingMessageCount(person.contacts,channel);
  const sendingChannels=new Set(person.contacts.filter(c=>replyInProgress(c,drafts[c.key],loadedAt)).map(c=>c.channel));
  const sending=channel==="all" ? sendingChannels.size>0 : sendingChannels.has(channel);
  const first = view.contact ?? person.contacts.find(contact => contact.pendingId) ?? person.contacts.find(contact => contact.needsReply) ?? person.contacts[0];
  if (!first) return null;
  return <li><button type="button" onClick={() => select(first)} aria-current={active ? "true" : undefined} className={cn("w-full px-3.5 py-3.5 text-left transition-colors hover:bg-[var(--app-surface-hover)]", active && "bg-[var(--app-surface-hover)]")}>
    <div className="flex items-start gap-2.5"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[12px] text-[var(--app-text-2)]">{view.name.replace(/^@/, "").slice(0, 1).toUpperCase() || "?"}</span><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><span className="truncate text-[12.5px] font-medium">{view.name}</span>{sending ? <Loader2 role="status" aria-label="Sending reply" className="h-4 w-4 shrink-0 animate-spin text-[var(--app-text-2)]"/> : messageCount > 0 && <span className="rounded-full bg-[var(--app-text)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--app-bg)]" title="Messages awaiting reply">{messageCount}</span>}</div>{view.contact && person.contacts.length > 1 && <p className="mt-0.5 truncate text-[9px] text-[var(--app-text-4)]">Linked · {person.name}</p>}<p className="mt-1 line-clamp-2 break-words text-[11px] leading-4 text-[var(--app-text-3)]">{view.preview || "No message preview"}</p><div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-[9px] text-[var(--app-text-4)]">{[...new Set(person.contacts.map(contact => contact.channel))].map(channel => mini ? <span key={channel} role="img" aria-label={`${CHANNEL_NAMES[channel]}${waiting.has(channel) ? " · awaiting reply" : " · linked account"}`} title={`${CHANNEL_NAMES[channel]}${waiting.has(channel) ? " · awaiting reply" : ""}`} data-channel={channel} data-waiting={waiting.has(channel)} className="mini-person-channel"><span aria-hidden="true" className="mini-channel-icon" style={{maskImage:`url(/social/${channel}.svg)`,WebkitMaskImage:`url(/social/${channel}.svg)`}} />{sendingChannels.has(channel) ? <Loader2 aria-label={`${CHANNEL_NAMES[channel]} reply sending`} className="h-3 w-3 animate-spin"/> : waitingMessageCount(person.contacts,channel)>0 && <span className="mini-channel-count">{waitingMessageCount(person.contacts,channel)}</span>}</span> : <span key={channel}>{CHANNEL_NAMES[channel]}</span>)}<span className="ml-auto">{view.lastActivityAt ? sourceTime(view.lastActivityAt) : ""}</span></div></div></div>
  </button></li>;
}

function InboxSkeleton() {
  return <div role="status" aria-label="Loading people" className="space-y-5 p-4">{[0, 1, 2, 3].map(item => <div key={item} className="animate-pulse space-y-2"><div className="h-3 w-28 rounded bg-[var(--app-surface-hover)]" /><div className="h-2 w-full rounded bg-[var(--app-surface-hover)]" /></div>)}</div>;
}
