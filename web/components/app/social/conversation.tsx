"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, FileText, Loader2, RefreshCw, Send, SkipForward, Sparkles } from "lucide-react";
import { skipSocialPending, submitSocialCommand } from "@/app/app/m/[id]/social/actions";
import type { SocialChannelState, SocialCommandInput, SocialContact, SocialMessage, SocialThread } from "@/lib/social-types";
import { cn } from "@/lib/utils";
import { PersonPanel } from "./person-panel";
import { CHANNEL_NAMES, commandLabel, freezeIntent, mergeMessages, mergeThread, sourceTime } from "./state";
import { useSocialResource } from "./use-resource";
import type { ComposerDraft, UpdateDraft } from "./workspace";

export function Conversation({ modelId, contact, channelState, draft, updateDraft, selectContact, refreshInbox }: {
  modelId: string; contact: SocialContact; channelState?: SocialChannelState; draft: ComposerDraft;
  updateDraft: UpdateDraft; selectContact: (contact: SocialContact) => void; refreshInbox: () => void;
}) {
  const params = new URLSearchParams({ channel: contact.channel, externalId: contact.externalId });
  const url = `/api/models/${modelId}/social/thread?${params}`;
  const resource = useSocialResource<SocialThread>(url, undefined, mergeThread);
  const thread = resource.data;
  const current = thread?.contact ?? contact;
  const [olderLoading, setOlderLoading] = useState(false);
  const [olderError, setOlderError] = useState("");
  const [skipLoading, setSkipLoading] = useState(false);
  const [briefOpen, setBriefOpen] = useState(false);
  const olderController = useRef<AbortController | null>(null);
  const actionBusy = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastSeenMessage = useRef<string | null>(null);
  const lastId = thread?.messages.at(-1)?.id;
  const waitingForCommand = thread?.commands.some(item => ["queued", "working", "sending"].includes(item.status)
    || (item.operation !== "regenerate" && item.status === "done" && ["queued", "ready", "pending", "leased", "approval"].includes(item.deliveryState ?? ""))) ?? false;
  const canSend = Boolean(thread && channelState?.available && channelState.connected && !resource.error);
  const blocked = !canSend || waitingForCommand || draft.submitting || skipLoading || Boolean(draft.retry);

  useEffect(() => () => { olderController.current?.abort(); }, []);
  useEffect(() => {
    if (!lastId) return;
    const scroll = scrollRef.current;
    if (!scroll) return;
    if (!lastSeenMessage.current || scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 130) scroll.scrollTop = scroll.scrollHeight;
    lastSeenMessage.current = lastId;
  }, [lastId]);

  function changeDraft(change: Partial<ComposerDraft>) {
    updateDraft(contact.key, previous => ({ ...previous, ...change }));
  }
  function refreshAll() { void resource.refresh(); refreshInbox(); }

  async function loadOlder() {
    if (!thread?.nextBefore || olderLoading) return;
    const controller = new AbortController();
    olderController.current?.abort(); olderController.current = controller;
    setOlderLoading(true); setOlderError("");
    const top = scrollRef.current?.scrollTop ?? 0;
    const height = scrollRef.current?.scrollHeight ?? 0;
    try {
      const response = await fetch(`${url}&before=${encodeURIComponent(thread.nextBefore)}`, { cache: "no-store", signal: controller.signal });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Could not load older messages.");
      if (controller.signal.aborted || body.contact?.key !== contact.key) return;
      const older = body as SocialThread;
      resource.update(previous => ({ ...previous, messages: mergeMessages(older.messages, previous.messages), hasMore: older.hasMore, nextBefore: older.nextBefore }));
      requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = top + scrollRef.current.scrollHeight - height; });
    } catch (error) { if (!controller.signal.aborted) setOlderError(error instanceof Error ? error.message : "Could not load older messages."); }
    finally { if (!controller.signal.aborted) setOlderLoading(false); }
  }

  async function submit(input: SocialCommandInput) {
    if (actionBusy.current || draft.submitting) return;
    actionBusy.current = true;
    changeDraft({ submitting: true, error: "", notice: "", retry: input });
    try {
      const result = await submitSocialCommand(modelId, input);
      if (result.error) {
        changeDraft({ error: result.error, retry: result.retryable ? input : null });
        if (!result.retryable) refreshAll();
      } else {
        updateDraft(contact.key, previous => ({ ...previous, retry: null, notice: result.command ? commandLabel(result.command) : result.message || "Request accepted.",
          text: input.operation === "send_text" && previous.text.trim() === input.text ? "" : previous.text }));
        if (result.command) resource.update(previous => ({ ...previous, commands: [result.command!, ...previous.commands.filter(command => command.id !== result.command!.id)] }));
        refreshAll();
      }
    } catch {
      changeDraft({ error: "The response was interrupted. Check the request using Retry; it keeps the same request ID and will not create a second send." });
    } finally { actionBusy.current = false; changeDraft({ submitting: false }); }
  }

  function command(operation: SocialCommandInput["operation"], text?: string, brief?: string) {
    if (!thread || blocked) return;
    const pending = thread.pending;
    if (operation !== "send_text" && !pending) return;
    const input = freezeIntent({ requestId: crypto.randomUUID(), operation, contactKey: thread.contact.key, expectedAccountScope: thread.contact.accountScope,
      expectedSourceId: thread.contact.lastMessageId, identityId: thread.contact.identityId,
      identityUpdatedAt: thread.contact.identityUpdatedAt,
      // A custom answer also replaces the exact draft currently visible, if any.
      ...(pending ? { pendingId: pending.id, expectedSuggestions: pending.suggestions } : {}),
      ...(text !== undefined ? { text } : {}), ...(brief !== undefined ? { brief } : {}) });
    void submit(input);
  }

  async function skip() {
    if (!thread?.pending || actionBusy.current || blocked) return;
    actionBusy.current = true; setSkipLoading(true); changeDraft({ error: "", notice: "" });
    const pending = thread.pending;
    try {
      const result = await skipSocialPending(modelId, pending.id, [...pending.suggestions]);
      if (result.error) changeDraft({ error: result.error });
      else { changeDraft({ notice: "Draft skipped." }); refreshAll(); }
    } catch { changeDraft({ error: "Could not skip this draft. Refresh and try again." }); }
    finally { actionBusy.current = false; setSkipLoading(false); }
  }

  return <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_200px]">
    <section className="app-card min-w-0 overflow-hidden" aria-label={`${CHANNEL_NAMES[contact.channel]} conversation with ${current.displayName}`}>
      <div className="border-b border-[var(--app-border)] px-4 py-3.5">
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="truncate text-[15px] font-medium">{current.displayName || current.username || current.externalId}</h2><p className="mt-0.5 text-[11px] text-[var(--app-text-3)]">{CHANNEL_NAMES[current.channel]}{current.username ? ` · @${current.username.replace(/^@/, "")}` : ""}{current.humanTakeover ? " · You are replying" : ""}</p></div><button type="button" disabled={resource.loading} onClick={() => void resource.refresh()} aria-label="Refresh conversation" className="app-btn app-btn-quiet h-8 w-8"><RefreshCw className={cn("h-3.5 w-3.5", resource.loading && "animate-spin")} /></button></div>
        {thread && thread.linkedContacts.length > 1 && <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Choose sending account">{thread.linkedContacts.map(linked => <button type="button" key={linked.key} onClick={() => selectContact(linked)} aria-pressed={linked.key === current.key} className={cn("rounded-md border px-2.5 py-1.5 text-[10.5px]", linked.key === current.key ? "border-[var(--app-text-3)] bg-[var(--app-surface-hover)] text-[var(--app-text)]" : "border-[var(--app-border)] text-[var(--app-text-3)]")}>{CHANNEL_NAMES[linked.channel]}</button>)}</div>}
      </div>
      {resource.error && <div role="alert" className="border-b border-[var(--app-border)] px-4 py-3 text-[11px] text-[#fca5a5]">{resource.error} {thread ? "Replies are disabled until the conversation refreshes." : ""}<button type="button" onClick={() => void resource.refresh()} className="ml-2 underline">Retry</button></div>}
      <div ref={scrollRef} className="h-[400px] overflow-y-auto overscroll-contain px-4 py-4 sm:h-[450px]" aria-label="Message history" aria-busy={!thread && resource.loading}>
        {!thread ? <div role="status" className="flex h-full items-center justify-center gap-2 text-[12px] text-[var(--app-text-3)]">{resource.loading ? <><Loader2 className="h-4 w-4 animate-spin" />Loading conversation</> : "Conversation could not be loaded."}</div> : <>
          {thread.hasMore && <div className="mb-4 text-center"><button type="button" onClick={() => void loadOlder()} disabled={olderLoading} className="app-btn app-btn-quiet mx-auto min-h-8 px-3 text-[11px]">{olderLoading && <Loader2 className="h-3 w-3 animate-spin" />}Load older messages</button></div>}
          {olderError && <p role="alert" className="mb-3 text-center text-[11px] text-[#fca5a5]">{olderError}</p>}
          {thread.messages.length === 0 ? <div className="flex h-full items-center justify-center text-center text-[12px] text-[var(--app-text-3)]">No imported messages for this account yet.</div> : <div className="space-y-3">{thread.messages.map(message => <Message key={message.id} message={message} />)}</div>}
        </>}
      </div>
      {thread?.pending && <div className="border-t border-[var(--app-border)] bg-white/[0.015] p-4">
        <div className="mb-3 flex items-center justify-between gap-2"><h3 className="flex items-center gap-1.5 text-[12px] font-medium"><Sparkles className="h-3.5 w-3.5" />Suggested replies</h3><span className="text-[10px] text-[var(--app-text-4)]">Waiting for you</span></div>
        {thread.pending.incomingPreview && <p className="mb-3 line-clamp-2 border-l border-[var(--app-border-strong)] pl-2.5 text-[11px] leading-5 text-[var(--app-text-3)]">{thread.pending.incomingPreview}</p>}
        <div className="space-y-2">{thread.pending.suggestions.map((rawSuggestion, index) => { const suggestion = thread.pending!.previews ? thread.pending!.previews[index] : rawSuggestion; return <div key={`${thread.pending!.id}-${index}-${rawSuggestion}`} className="rounded-lg border border-[var(--app-border)] bg-[var(--app-bg)] p-3"><p className="whitespace-pre-wrap break-words text-[12px] leading-5">{suggestion || "This suggestion cannot be sent as text. Regenerate a new reply."}</p><div className="mt-2 flex justify-end"><button type="button" onClick={() => command("approve", suggestion || "")} disabled={blocked || !suggestion} className="app-btn app-btn-ghost min-h-8 px-2.5 text-[10.5px]"><Check className="h-3 w-3" />Approve reply {index + 1}</button></div></div>; })}</div>
        {thread.pending.suggestions.length === 0 && <p className="text-[11px] text-[var(--app-text-3)]">No text suggestions yet. Regenerate a draft or write your own reply.</p>}
        {thread.pending.hint && <p className="mt-2 text-[10.5px] text-[var(--app-text-4)]">{thread.pending.hint}</p>}
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2"><button type="button" disabled={blocked} onClick={() => command("regenerate", undefined, draft.brief.trim())} className="inline-flex min-h-8 items-center gap-1.5 text-[11px] text-[var(--app-text-2)] disabled:opacity-40"><RefreshCw className="h-3 w-3" />Regenerate</button><button type="button" onClick={() => setBriefOpen(!briefOpen)} aria-expanded={briefOpen} className="inline-flex min-h-8 items-center gap-1 text-[11px] text-[var(--app-text-3)]">Add direction<ChevronDown className={cn("h-3 w-3", briefOpen && "rotate-180")} /></button><button type="button" disabled={blocked} onClick={() => void skip()} className="ml-auto inline-flex min-h-8 items-center gap-1 text-[11px] text-[var(--app-text-3)] disabled:opacity-40">{skipLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <SkipForward className="h-3 w-3" />}Skip</button></div>
        {briefOpen && <label className="mt-2 block"><span className="text-[10.5px] text-[var(--app-text-3)]">Direction for the next draft</span><textarea value={draft.brief} onChange={event => changeDraft({ brief: event.target.value })} maxLength={2000} rows={2} placeholder="Keep it warm and ask about his weekend…" className="app-input mt-1 resize-y text-[12px]!" /><span className="mt-1 block text-[10px] text-[var(--app-text-4)]">Used when you choose Regenerate.</span></label>}
      </div>}
      <form onSubmit={event => { event.preventDefault(); if (draft.text.trim()) command("send_text", draft.text.trim()); }} className="border-t border-[var(--app-border)] p-4">
        <label htmlFor={`reply-${current.channel}`} className="mb-2 flex items-center justify-between gap-2 text-[11px] font-medium"><span>Reply on {CHANNEL_NAMES[current.channel]}</span><span className="truncate font-normal text-[var(--app-text-4)]">To {current.displayName || current.username || current.externalId}</span></label>
        <textarea id={`reply-${current.channel}`} value={draft.text} onChange={event => changeDraft({ text: event.target.value })} onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); if (draft.text.trim()) command("send_text", draft.text.trim()); } }} rows={3} maxLength={12000} placeholder="Write your own reply…" className="app-input resize-y text-[12px]! leading-5!" />
        {draft.error && <p role="alert" className="mt-2 text-[11px] leading-5 text-[#fca5a5]">{draft.error}</p>}
        {draft.retry && !draft.submitting && <button type="button" onClick={() => void submit(draft.retry!)} className="app-btn app-btn-ghost mt-2 min-h-8 px-3 text-[11px]">Retry the same request</button>}
        {draft.notice && <p role="status" className="mt-2 text-[11px] text-[var(--app-text-3)]">{draft.notice}</p>}
        <div className="mt-3 flex items-center justify-between gap-3"><p className="max-w-[65%] text-[10px] leading-4 text-[var(--app-text-4)]">{!channelState?.connected ? "Connect this channel before replying." : waitingForCommand ? "A request is in progress. Its delivery status appears below." : channelState.mode === "auto" ? "Your reply takes over this conversation. AI pauses here until you resume it." : "Sends your exact text. Ctrl / ⌘ + Enter to send."}</p><button type="submit" disabled={blocked || !draft.text.trim()} className="app-btn app-btn-primary min-h-9 shrink-0 px-3 text-[11px]">{draft.submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}Send</button></div>
      </form>
      {thread && thread.commands.length > 0 && <div className="border-t border-[var(--app-border)] px-4 py-3"><h3 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[var(--app-text-4)]">Recent requests</h3><ul className="space-y-2">{thread.commands.slice(0, 5).map(item => <li key={item.id} className="text-[10.5px]"><div className="flex justify-between gap-2"><span className={cn(["failed", "uncertain", "blocked", "stale"].includes(item.status) ? "text-[#fca5a5]" : "text-[var(--app-text-2)]")}>{commandLabel(item)}</span><span className="text-[var(--app-text-4)]">{sourceTime(item.createdAt)}</span></div>{item.text && <p className="mt-0.5 line-clamp-2 break-words text-[var(--app-text-3)]">{item.text}</p>}{item.reason && <p className="mt-0.5 break-words text-[var(--app-text-4)]">{item.reason}</p>}{(item.status === "uncertain" || item.deliveryState === "uncertain") && <p className="mt-1 text-[#fca5a5]">Check the channel before sending again. This request will not be resent automatically.</p>}</li>)}</ul></div>}
    </section>
    {thread && <PersonPanel key={current.key} modelId={modelId} thread={thread} selectContact={selectContact} refresh={refreshAll} />}
  </div>;
}

function Message({ message }: { message: SocialMessage }) {
  const own = message.role === "assistant";
  const attachment = message.attachment;
  return <div className={cn("flex", own ? "justify-end" : "justify-start")}><div className={cn("max-w-[88%] rounded-xl px-3 py-2.5 text-[12px] leading-5", own ? "rounded-br-sm bg-[#252525] text-[var(--app-text)]" : "rounded-bl-sm border border-[var(--app-border)] bg-[#131313] text-[var(--app-text-2)]")}>
    {attachment && <div className="mb-2">{attachment.url && ["image", "photo"].includes(attachment.kind) ? <a href={attachment.url} target="_blank" rel="noopener noreferrer"><Image src={attachment.url} alt="Message attachment" width={480} height={360} unoptimized className="max-h-64 w-auto rounded-md object-contain" /></a> : attachment.url && ["audio", "voice"].includes(attachment.kind) ? <audio controls preload="none" src={attachment.url} className="max-w-full" aria-label="Audio message" /> : attachment.url && attachment.kind === "video" ? <video controls preload="none" src={attachment.url} className="max-h-64 max-w-full rounded-md" aria-label="Video message" /> : <span className="inline-flex items-center gap-1.5 text-[11px] text-[var(--app-text-3)]"><FileText className="h-3 w-3" />{attachment.url ? <a href={attachment.url} target="_blank" rel="noopener noreferrer" className="underline">Open {attachment.kind} attachment</a> : `${attachment.kind} attachment · preview unavailable`}</span>}</div>}
    {message.content && <p className="whitespace-pre-wrap break-words">{message.content}</p>}
    <p className="mt-1 text-right text-[9px] leading-4 text-[var(--app-text-4)]" title={message.occurredAt ? `${message.occurredAt} · original message time` : "Original message time is unknown. Import time is not shown as message time."}>{sourceTime(message.occurredAt)}</p>
  </div></div>;
}
