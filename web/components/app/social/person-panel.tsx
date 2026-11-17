"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, Link2, Loader2, Pause, Play, Search, Unlink, X } from "lucide-react";
import { useSocialTransport } from "./transport";
import type { SocialContact, SocialResult, SocialSnapshot, SocialThread } from "@/lib/social-types";
import { cn } from "@/lib/utils";
import { CHANNEL_NAMES } from "./state";
import { useSocialResource } from "./use-resource";

export function PersonPanel({ modelId, thread, selectContact, refresh }: {
  modelId: string; thread: SocialThread; selectContact: (contact: SocialContact) => void; refresh: () => void;
}) {
  const { transport: { linkSocialContacts, setSocialTakeover, unlinkSocialContact } } = useSocialTransport();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [linkTarget, setLinkTarget] = useState<SocialContact | null>(null);
  const [unlinkTarget, setUnlinkTarget] = useState<SocialContact | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const contact = thread.contact;
  const accounts = thread.linkedContacts.length ? thread.linkedContacts : [contact];

  async function run(action: () => Promise<SocialResult>): Promise<boolean> {
    if (lock.current) return false;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const result = await action();
      if (result.error) { setError(result.error); return false; }
      setNotice(result.message || "Saved."); refresh(); return true;
    } catch { setError("Could not save. Refresh and try again."); return false; }
    finally { lock.current = false; setBusy(false); }
  }

  function chooseLink(target: SocialContact) { setError(""); setPickerOpen(false); setLinkTarget(target); }

  return <aside className="space-y-3" aria-label="Person and linked accounts">
    <div className="app-card p-3.5"><h3 className="text-[11px] font-medium">Linked accounts <span className="ml-1 text-[var(--app-text-4)]">{accounts.length}</span></h3><p className="mt-1.5 text-[10px] leading-4 text-[var(--app-text-4)]">Confirmed accounts share conversation context.</p>
      <ul className="mt-3 space-y-2.5">{accounts.map(account => <li key={account.key} className="flex items-center gap-1"><button type="button" onClick={() => selectContact(account)} className={cn("min-w-0 flex-1 rounded-md px-2 py-2 text-left", account.key === contact.key ? "bg-[var(--app-surface-hover)]" : "hover:bg-[var(--app-surface-hover)]")}><span className="block text-[10px] text-[var(--app-text-4)]">{CHANNEL_NAMES[account.channel]}</span><span className="mt-0.5 block truncate text-[11px]">{account.username ? `@${account.username.replace(/^@/, "")}` : account.displayName || account.externalId}</span></button>{accounts.length > 1 && <button type="button" disabled={busy} aria-label={`Separate ${CHANNEL_NAMES[account.channel]} account ${account.displayName}`} title="Separate this account" onClick={() => { setError(""); setUnlinkTarget(account); }} className="app-btn app-btn-quiet h-8 w-7 shrink-0"><Unlink className="h-3 w-3" /></button>}</li>)}</ul>
      <button type="button" onClick={() => { setError(""); setPickerOpen(true); }} disabled={busy} className="app-btn app-btn-ghost mt-3 min-h-8 w-full px-2 text-[10.5px]"><Link2 className="h-3 w-3" />Link another account</button>
    </div>
    {thread.candidate && !accounts.some(account => account.key === thread.candidate!.key) && <div className="app-card p-3.5"><h3 className="text-[11px] font-medium">Possible match</h3><p className="mt-2 break-words text-[11px] leading-5 text-[var(--app-text-3)]">{thread.candidate.displayName || thread.candidate.username} on {CHANNEL_NAMES[thread.candidate.channel]}</p><p className="mt-1 text-[10px] leading-4 text-[var(--app-text-4)]">Still separate. Review before sharing history.</p><button type="button" disabled={busy} onClick={() => chooseLink(thread.candidate!)} className="app-btn app-btn-ghost mt-3 min-h-8 w-full px-2 text-[10.5px]">Review match</button></div>}
    <div className="app-card p-3.5"><h3 className="text-[11px] font-medium">{CHANNEL_NAMES[contact.channel]} control</h3><p className="mt-2 text-[10.5px] leading-5 text-[var(--app-text-3)]">{contact.humanTakeover || !contact.aiEnabled ? "You are managing this conversation. AI is paused for this account." : "This conversation follows the channel's reply mode."}</p><button type="button" disabled={busy} onClick={() => void run(() => setSocialTakeover(modelId, contact.key, !(contact.humanTakeover || !contact.aiEnabled)))} className="app-btn app-btn-ghost mt-3 min-h-8 w-full px-2 text-[10.5px]">{busy ? <Loader2 className="h-3 w-3 animate-spin" /> : contact.humanTakeover || !contact.aiEnabled ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}{contact.humanTakeover || !contact.aiEnabled ? "Resume AI" : "Take over"}</button><p className="mt-2 text-[9.5px] leading-4 text-[var(--app-text-4)]">Resume follows the channel mode. Manual stays manual.</p></div>
    {contact.summary && <details className="app-card p-3.5"><summary className="cursor-pointer text-[11px] font-medium">What she remembers</summary><p className="mt-3 whitespace-pre-wrap break-words text-[11px] leading-5 text-[var(--app-text-3)]">{contact.summary}</p></details>}
    {contact.spentCents > 0 && <div className="app-card p-3.5"><p className="text-[10px] text-[var(--app-text-4)]">Fanvue spending</p><p className="mt-1 text-[16px] font-medium">{new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(contact.spentCents / 100)}</p></div>}
    {error && <p role="alert" className="px-1 text-[11px] leading-5 text-[#fca5a5]">{error}</p>}
    {notice && <p role="status" className="px-1 text-[10.5px] text-[var(--app-text-3)]">{notice}</p>}
    {pickerOpen && <Dialog title="Find their other account" close={() => setPickerOpen(false)}><ContactPicker modelId={modelId} current={contact} linked={accounts} choose={chooseLink} /></Dialog>}
    {linkTarget && <Dialog title="Confirm the same person" busy={busy} close={() => setLinkTarget(null)}>
      <div className="space-y-2 rounded-lg border border-[var(--app-border)] p-3 text-[12px]"><AccountLabel contact={contact} /><AccountLabel contact={linkTarget} /></div>
      <p className="mt-4 text-[12px] leading-6 text-[var(--app-text-3)]">Confirm only if both accounts belong to the same person. Their private conversation history will be shared across these channels. Existing drafts and queued context decisions will be invalidated.</p>
      {error && <p role="alert" className="mt-3 text-[12px] text-[#fca5a5]">{error}</p>}
      <div className="mt-5 grid gap-2 sm:flex sm:justify-end"><button type="button" disabled={busy} onClick={() => setLinkTarget(null)} className="app-btn app-btn-ghost min-h-9 px-3">Cancel</button><button type="button" disabled={busy} onClick={async () => { if (await run(() => linkSocialContacts(modelId, contact.key, linkTarget.key))) setLinkTarget(null); }} className="app-btn app-btn-primary min-h-9 px-3">{busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Confirm and share history</button></div>
    </Dialog>}
    {unlinkTarget && <Dialog title="Separate this account?" busy={busy} close={() => setUnlinkTarget(null)}><AccountLabel contact={unlinkTarget} /><p className="mt-3 text-[12px] leading-6 text-[var(--app-text-3)]">This account will become a separate person. Future replies will stop using the other accounts&apos; history, and existing drafts will be invalidated.</p>{error && <p role="alert" className="mt-3 text-[12px] text-[#fca5a5]">{error}</p>}<div className="mt-5 grid gap-2 sm:flex sm:justify-end"><button type="button" disabled={busy} onClick={() => setUnlinkTarget(null)} className="app-btn app-btn-ghost min-h-9 px-3">Keep linked</button><button type="button" disabled={busy} onClick={async () => { if (await run(() => unlinkSocialContact(modelId, unlinkTarget.key))) setUnlinkTarget(null); }} className="app-btn app-btn-primary min-h-9 px-3">{busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Separate account</button></div></Dialog>}
  </aside>;
}

function AccountLabel({ contact }: { contact: SocialContact }) {
  return <p className="break-words text-[12px]"><span className="text-[var(--app-text-4)]">{CHANNEL_NAMES[contact.channel]} · </span>{contact.displayName || contact.username || contact.externalId}{contact.username ? ` (@${contact.username.replace(/^@/, "")})` : ""}</p>;
}

function Dialog({ title, children, close, busy = false }: { title: string; children: ReactNode; close: () => void; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} onCancel={event => { event.preventDefault(); if (!busy) close(); }} aria-labelledby="social-dialog-title" className="m-auto max-h-[85dvh] w-[min(440px,calc(100vw-32px))] overflow-y-auto rounded-xl border border-[var(--app-border-strong)] bg-[#101010] p-5 text-[var(--app-text)] shadow-2xl backdrop:bg-black/75"><div className="mb-4 flex items-center justify-between gap-3"><h2 id="social-dialog-title" className="text-[16px] font-medium">{title}</h2><button type="button" disabled={busy} onClick={close} aria-label="Close dialog" className="app-btn app-btn-quiet h-8 w-8"><X className="h-4 w-4" /></button></div>{children}</dialog>;
}

function ContactPicker({ modelId, current, linked, choose }: { modelId: string; current: SocialContact; linked: SocialContact[]; choose: (contact: SocialContact) => void }) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState({ search: "", offset: 0 });
  useEffect(() => { const timer = window.setTimeout(() => setQuery(previous => previous.search === search.trim() ? previous : { search: search.trim(), offset: 0 }), 300); return () => window.clearTimeout(timer); }, [search]);
  const params = new URLSearchParams({ search: query.search, channel: "all", filter: "all", offset: String(query.offset) });
  const resource = useSocialResource<SocialSnapshot>(`/api/models/${modelId}/social?${params}`);
  const choices = resource.data?.people.flatMap(person => person.contacts).filter(contact => contact.channel !== current.channel && !linked.some(account => account.key === contact.key)) ?? [];
  return <><label className="relative block"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-[var(--app-text-4)]" /><input autoFocus type="search" value={search} onChange={event => setSearch(event.target.value)} aria-label="Search accounts to link" placeholder="Name or username on another channel" className="app-input pl-10! text-[12px]!" /></label>
    <p className="mt-2 text-[10.5px] text-[var(--app-text-4)]">Only accounts with imported conversations appear here.</p>
    {resource.error && <p role="alert" className="mt-3 text-[11px] text-[#fca5a5]">{resource.error}<button type="button" onClick={() => void resource.refresh()} className="ml-2 underline">Retry</button></p>}
    <div className="my-3 max-h-64 overflow-y-auto">{!resource.data && resource.loading ? <p role="status" className="py-6 text-center text-[12px] text-[var(--app-text-3)]">Loading accounts…</p> : choices.length === 0 ? <p className="py-6 text-center text-[12px] text-[var(--app-text-3)]">No other accounts on this page. Try a name or the next page.</p> : <ul className="divide-y divide-[var(--app-border)]">{choices.map(contact => <li key={contact.key}><button type="button" onClick={() => choose(contact)} className="w-full rounded-md px-2 py-3 text-left hover:bg-[var(--app-surface-hover)]"><AccountLabel contact={contact} /></button></li>)}</ul>}</div>
    {resource.data && resource.data.total > resource.data.pageSize && <div className="flex items-center justify-between border-t border-[var(--app-border)] pt-3 text-[10.5px] text-[var(--app-text-4)]"><span>Page {Math.floor(query.offset / resource.data.pageSize) + 1}</span><div className="flex gap-1"><button type="button" disabled={query.offset === 0 || resource.loading} onClick={() => setQuery(previous => ({ ...previous, offset: Math.max(0, previous.offset - resource.data!.pageSize) }))} aria-label="Previous accounts" className="app-btn app-btn-quiet h-8 w-8"><ChevronLeft className="h-4 w-4" /></button><button type="button" disabled={query.offset + resource.data.pageSize >= resource.data.total || resource.loading} onClick={() => setQuery(previous => ({ ...previous, offset: previous.offset + resource.data!.pageSize }))} aria-label="Next accounts" className="app-btn app-btn-quiet h-8 w-8"><ChevronRight className="h-4 w-4" /></button></div></div>}
  </>;
}
